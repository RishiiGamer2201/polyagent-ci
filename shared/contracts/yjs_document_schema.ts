/**
 * PolyAgent CI — Yjs CRDT Document Schema
 * 
 * Single source of truth for the Yjs document structure used by the
 * collaborative Markdown editor. All agents MUST conform to this schema.
 * 
 * Yjs Types Used:
 *   - Y.Text  → Conflict-free rich text (markdown content)
 *   - Y.Map   → Key-value metadata store
 *   - Y.Array → Ordered lists (version history)
 * 
 * CONTRACT CHANGE PROTOCOL:
 *   1. Propose change in team_context.md
 *   2. Check which agents have consumed this contract
 *   3. Issue targeted reconciliation prompts
 *   4. Then update this file
 */

import * as Y from "yjs";

// ═══════════════════════════════════════════════════════════
// Root Document Structure
// ═══════════════════════════════════════════════════════════

/**
 * The root Y.Doc contains three top-level shared types.
 * Access them via:
 *   doc.getText("content")
 *   doc.getMap("metadata")
 *   doc.getMap("awareness")
 */

export interface CollaborativeDocument {
  /**
   * "content" — Y.Text
   * 
   * The markdown content of the document. This is the primary
   * editable region bound to CodeMirror 6 via y-codemirror.next.
   * 
   * Supports:
   *   - Concurrent insertions/deletions (CRDT-resolved)
   *   - Undo/redo via Y.UndoManager scoped to this text
   *   - Character-level conflict resolution
   */
  content: Y.Text;

  /**
   * "metadata" — Y.Map<DocumentMetadata>
   * 
   * Document-level metadata. Updated via Y.Map.set() operations.
   * Changes here are synced but do NOT trigger CodeMirror updates.
   */
  metadata: Y.Map<any>; // typed as DocumentMetadata below

  /**
   * "awareness" — NOT stored in Y.Doc
   * 
   * Cursor positions and user presence are handled by the
   * Yjs Awareness protocol (separate from document state).
   * See: websocket_messages.ts for the wire format.
   */
}

// ═══════════════════════════════════════════════════════════
// Metadata Schema (stored in Y.Map "metadata")
// ═══════════════════════════════════════════════════════════

export interface DocumentMetadata {
  /** Document UUID (matches REST API document ID) */
  documentId: string;

  /** Human-readable title */
  title: string;

  /** User ID of the document creator */
  ownerId: string;

  /** ISO 8601 timestamp of creation */
  createdAt: string;

  /** ISO 8601 timestamp of last content modification */
  lastModifiedAt: string;

  /** User ID of last modifier */
  lastModifiedBy: string;

  /** Monotonically increasing version counter */
  version: number;

  /** Word count (updated on content change, debounced 500ms) */
  wordCount: number;

  /** Character count */
  charCount: number;

  /** Document tags for organization */
  tags: string[];
}

// ═══════════════════════════════════════════════════════════
// Awareness State (Yjs Awareness protocol, NOT in Y.Doc)
// ═══════════════════════════════════════════════════════════

/**
 * Each connected client maintains an awareness state.
 * This is the structure set via awareness.setLocalState().
 * 
 * Access:  
 *   const awareness = provider.awareness;
 *   awareness.setLocalState(localState);
 *   awareness.getStates(); // Map<clientId, AwarenessState>
 */
export interface AwarenessState {
  /** User info */
  user: {
    userId: string;
    username: string;
    /** CSS color for cursor rendering (e.g., "#FF6B6B") */
    color: string;
  };

  /** Current cursor/selection in CodeMirror */
  cursor: {
    /** Absolute anchor position */
    anchor: number;
    /** Absolute head position (== anchor if no selection) */
    head: number;
  } | null;

  /** Activity indicator */
  status: "active" | "idle" | "away";

  /** ISO 8601 timestamp of last keystroke or cursor move */
  lastActive: string;
}

// ═══════════════════════════════════════════════════════════
// Y.Doc Initialization
// ═══════════════════════════════════════════════════════════

/**
 * Creates a new Y.Doc with the correct shared type structure.
 * Both Frontend and Backend MUST use this function (or equivalent)
 * to ensure schema consistency.
 * 
 * Usage:
 *   const { doc, content, metadata } = createCollaborativeDoc("doc-uuid");
 */
export function createCollaborativeDoc(documentId: string) {
  const doc = new Y.Doc();

  // Get or create shared types (idempotent in Yjs)
  const content = doc.getText("content");
  const metadata = doc.getMap("metadata") as Y.Map<any>;

  // Initialize metadata with defaults (only if empty)
  if (metadata.size === 0) {
    const now = new Date().toISOString();
    metadata.set("documentId", documentId);
    metadata.set("title", "Untitled Document");
    metadata.set("ownerId", "");
    metadata.set("createdAt", now);
    metadata.set("lastModifiedAt", now);
    metadata.set("lastModifiedBy", "");
    metadata.set("version", 0);
    metadata.set("wordCount", 0);
    metadata.set("charCount", 0);
    metadata.set("tags", []);
  }

  return { doc, content, metadata };
}

// ═══════════════════════════════════════════════════════════
// Undo Manager Configuration
// ═══════════════════════════════════════════════════════════

/**
 * Configure Y.UndoManager for the content text type.
 * Scoped to the local user's changes only (collaborative-aware undo).
 * 
 * Usage:
 *   const undoManager = createUndoManager(content);
 *   undoManager.undo();
 *   undoManager.redo();
 */
export function createUndoManager(content: Y.Text): Y.UndoManager {
  return new Y.UndoManager(content, {
    // Capture timeout: group rapid edits into single undo steps
    captureTimeout: 500,
    // Track origins to scope undo to local changes only
    trackedOrigins: new Set([null, "local"]),
  });
}

// ═══════════════════════════════════════════════════════════
// Version Negotiation
// ═══════════════════════════════════════════════════════════

/**
 * Schema version for compatibility checking between clients.
 * 
 * When a client connects:
 * 1. Client sends its SCHEMA_VERSION in the initial handshake
 * 2. Server compares with its own SCHEMA_VERSION
 * 3. If major versions differ → reject with DOC_ERROR
 * 4. If minor versions differ → allow but log warning
 * 
 * Bump rules:
 *   - MAJOR: Breaking changes to shared type names or structure
 *   - MINOR: New optional metadata fields
 *   - PATCH: Bug fixes in initialization logic
 */
export const SCHEMA_VERSION = "1.0.0";

/**
 * Shared type names — canonical strings used to access Y.Doc types.
 * Use these constants instead of raw strings to prevent typos.
 */
export const SHARED_TYPES = {
  CONTENT:   "content",    // Y.Text — markdown body
  METADATA:  "metadata",   // Y.Map  — document info
} as const;

// ═══════════════════════════════════════════════════════════
// Encoding / Persistence
// ═══════════════════════════════════════════════════════════

/**
 * Server-side persistence format:
 * 
 * The Backend stores the Y.Doc state as a binary blob using:
 *   Y.encodeStateAsUpdate(doc) → Uint8Array → store in Redis/DB
 * 
 * To restore:
 *   Y.applyUpdate(doc, storedUpdate)
 * 
 * Redis keys:
 *   - `ydoc:${documentId}:state`    → Latest full state (binary)
 *   - `ydoc:${documentId}:updates`  → Pending incremental updates (list)
 *   - `ydoc:${documentId}:awareness` → Current awareness states (hash)
 * 
 * Compaction: After 100 incremental updates, merge into full state.
 */
export const REDIS_KEY_PATTERNS = {
  STATE:     (docId: string) => `ydoc:${docId}:state`,
  UPDATES:   (docId: string) => `ydoc:${docId}:updates`,
  AWARENESS: (docId: string) => `ydoc:${docId}:awareness`,
} as const;

/** Compact after this many incremental updates */
export const COMPACTION_THRESHOLD = 100;
