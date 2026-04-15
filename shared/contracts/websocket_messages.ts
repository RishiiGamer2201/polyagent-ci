/**
 * PolyAgent CI — WebSocket Message Contracts
 * 
 * Single source of truth for all WebSocket message shapes exchanged
 * between the Frontend (React + CodeMirror 6) and Backend (FastAPI).
 * 
 * Protocol: Yjs WebSocket Sync Protocol (binary + JSON control frames)
 * Transport: WebSocket at /ws/{document_id}?token=<jwt>
 * 
 * CONTRACT CHANGE PROTOCOL:
 *   1. Propose change in team_context.md
 *   2. Check which agents have consumed this contract
 *   3. Issue targeted reconciliation prompts
 *   4. Then update this file
 */

// ═══════════════════════════════════════════════════════════
// Message Type Enum
// ═══════════════════════════════════════════════════════════

export enum MessageType {
  // Yjs sync protocol (binary frames)
  SYNC_STEP_1       = 0,   // Server → Client: Full document state vector
  SYNC_STEP_2       = 1,   // Client → Server: Missing updates response
  SYNC_UPDATE       = 2,   // Bidirectional: Incremental document update

  // Awareness protocol (JSON frames)
  AWARENESS_UPDATE  = 3,   // Bidirectional: Cursor position & user presence
  AWARENESS_QUERY   = 4,   // Client → Server: Request current awareness states

  // Control messages (JSON frames)
  AUTH_OK           = 10,  // Server → Client: Authentication confirmed
  AUTH_ERROR        = 11,  // Server → Client: Authentication failed
  DOC_LOADED        = 12,  // Server → Client: Document ready for editing
  DOC_ERROR         = 13,  // Server → Client: Document load failed
  USER_JOINED       = 14,  // Server → Client: A user joined the document
  USER_LEFT         = 15,  // Server → Client: A user left the document
  PING              = 20,  // Client → Server: Heartbeat
  PONG              = 21,  // Server → Client: Heartbeat response
  ERROR             = 99,  // Server → Client: General error
}

// ═══════════════════════════════════════════════════════════
// Binary Frame Layout (Yjs Sync Protocol)
// ═══════════════════════════════════════════════════════════

/**
 * Binary frames follow this layout:
 * 
 * ┌──────────┬───────────────────────────────┐
 * │ byte 0   │ MessageType (uint8)           │
 * ├──────────┼───────────────────────────────┤
 * │ bytes 1+ │ Yjs-encoded payload (Uint8Array) │
 * └──────────┴───────────────────────────────┘
 * 
 * Use lib0 encoding/decoding for the payload.
 */

export interface BinaryFrame {
  /** First byte: message type discriminator */
  type: MessageType.SYNC_STEP_1 | MessageType.SYNC_STEP_2 | MessageType.SYNC_UPDATE;
  /** Remaining bytes: Yjs-encoded data */
  payload: Uint8Array;
}

// ═══════════════════════════════════════════════════════════
// Awareness Messages (JSON frames)
// ═══════════════════════════════════════════════════════════

export interface CursorPosition {
  /** Absolute character offset in the document */
  anchor: number;
  /** Selection end (same as anchor if no selection) */
  head: number;
  /** Line number (0-indexed) for quick rendering */
  line: number;
  /** Column number (0-indexed) */
  column: number;
}

export interface UserPresence {
  /** Unique user identifier (UUID from JWT) */
  userId: string;
  /** Display name */
  username: string;
  /** CSS color for cursor/selection highlighting */
  color: string;
  /** Current cursor position, null if user has no focus */
  cursor: CursorPosition | null;
  /** ISO 8601 timestamp of last activity */
  lastActive: string;
}

export interface AwarenessUpdateMessage {
  type: MessageType.AWARENESS_UPDATE;
  /** Client ID assigned by Yjs awareness protocol */
  clientId: number;
  /** The updated presence state */
  presence: UserPresence;
  /** Timestamp for ordering */
  timestamp: string;
}

export interface AwarenessQueryMessage {
  type: MessageType.AWARENESS_QUERY;
  /** Document ID to query awareness for */
  documentId: string;
}

// ═══════════════════════════════════════════════════════════
// Control Messages (JSON frames)
// ═══════════════════════════════════════════════════════════

export interface AuthOkMessage {
  type: MessageType.AUTH_OK;
  userId: string;
  username: string;
  /** Assigned client color for this session */
  assignedColor: string;
  /** Yjs client ID for this connection */
  clientId: number;
}

export interface AuthErrorMessage {
  type: MessageType.AUTH_ERROR;
  reason: "INVALID_TOKEN" | "TOKEN_EXPIRED" | "UNAUTHORIZED";
  detail: string;
}

export interface DocLoadedMessage {
  type: MessageType.DOC_LOADED;
  documentId: string;
  title: string;
  /** Number of currently connected collaborators */
  activeUsers: number;
  /** Server Yjs document version for consistency check */
  version: number;
}

export interface DocErrorMessage {
  type: MessageType.DOC_ERROR;
  documentId: string;
  reason: "NOT_FOUND" | "ACCESS_DENIED" | "LOAD_FAILED";
  detail: string;
}

export interface UserJoinedMessage {
  type: MessageType.USER_JOINED;
  userId: string;
  username: string;
  color: string;
  /** Updated count of active users */
  activeUsers: number;
  timestamp: string;
}

export interface UserLeftMessage {
  type: MessageType.USER_LEFT;
  userId: string;
  username: string;
  /** Updated count of active users */
  activeUsers: number;
  timestamp: string;
}

export interface PingMessage {
  type: MessageType.PING;
  timestamp: string;
}

export interface PongMessage {
  type: MessageType.PONG;
  timestamp: string;
  /** Server processing latency in ms */
  serverTime: number;
}

export interface ErrorMessage {
  type: MessageType.ERROR;
  code: string;
  detail: string;
  /** Whether the client should reconnect */
  recoverable: boolean;
}

// ═══════════════════════════════════════════════════════════
// Union Types
// ═══════════════════════════════════════════════════════════

/** All possible messages from Server → Client */
export type ServerMessage =
  | AuthOkMessage
  | AuthErrorMessage
  | DocLoadedMessage
  | DocErrorMessage
  | UserJoinedMessage
  | UserLeftMessage
  | PongMessage
  | AwarenessUpdateMessage
  | ErrorMessage;

/** All possible messages from Client → Server */
export type ClientMessage =
  | AwarenessUpdateMessage
  | AwarenessQueryMessage
  | PingMessage;

/** Bidirectional messages (both binary sync + awareness) */
export type BidirectionalMessage =
  | BinaryFrame
  | AwarenessUpdateMessage;

/** All WebSocket messages (for generic handlers) */
export type WebSocketMessage = ServerMessage | ClientMessage | BidirectionalMessage;

// ═══════════════════════════════════════════════════════════
// Connection Lifecycle
// ═══════════════════════════════════════════════════════════

/**
 * Connection Flow:
 *
 * 1. Client opens WebSocket: /ws/{document_id}?token=<jwt>
 * 2. Server validates JWT
 *    ├─ Success → AuthOkMessage + DocLoadedMessage
 *    └─ Failure → AuthErrorMessage (connection closed)
 * 3. Server sends SyncStep1 (binary: full state vector)
 * 4. Client responds with SyncStep2 (binary: missing updates)
 * 5. Real-time editing loop:
 *    ├─ SyncUpdate (binary, bidirectional) for document changes
 *    ├─ AwarenessUpdate (JSON, bidirectional) for cursor/presence
 *    ├─ UserJoined / UserLeft (JSON, server → client) for presence
 *    └─ Ping / Pong (JSON) for keepalive (every 30s)
 * 6. Client disconnects → Server broadcasts UserLeftMessage
 *
 * Reconnection: Client should use exponential backoff (1s, 2s, 4s, max 30s)
 * On reconnect, full sync cycle (steps 2-4) repeats automatically.
 */
