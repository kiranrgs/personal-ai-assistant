import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  addBookmark,
  Bookmark,
  ChatMessage,
  confirmAction,
  getChatHistory,
  listBookmarks,
  Me,
  removeBookmark,
  sendChatMessage,
} from "../lib/apiClient";

export default function Chat({ me, onSignOut }: { me: Me; onSignOut: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ action_id: string; summary: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadHistory();
    void loadBookmarks();
  }, []);

  async function loadHistory() {
    const { messages } = await getChatHistory(100);
    setMessages(messages);
  }

  async function loadBookmarks() {
    const { bookmarks } = await listBookmarks();
    setBookmarks(bookmarks);
  }

  function bookmarkFor(messageId: number): Bookmark | undefined {
    return bookmarks.find((b) => b.message_id === messageId);
  }

  async function toggleBookmark(messageId: number) {
    const existing = bookmarkFor(messageId);
    if (existing) {
      await removeBookmark(existing.id);
    } else {
      await addBookmark(messageId);
    }
    await loadBookmarks();
  }

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || sending) return;
    setError(null);
    setSending(true);
    const text = input;
    setInput("");
    try {
      const result = await sendChatMessage(text);
      setPendingAction(result.pending_action);
      await loadHistory();
    } catch {
      setError("Failed to send message.");
    } finally {
      setSending(false);
    }
  }

  async function handleConfirm(approved: boolean) {
    if (!pendingAction) return;
    try {
      await confirmAction(pendingAction.action_id, approved);
    } finally {
      setPendingAction(null);
      await loadHistory();
    }
  }

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <strong>{me.email}</strong>
          <Link to="/settings">Settings</Link>
          <button className="link-button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
        <h2>Bookmarks</h2>
        <ul className="bookmark-list">
          {bookmarks.map((b) => (
            <li key={b.id}>
              <span>{b.messages?.content ?? `Message #${b.message_id}`}</span>
              <button className="link-button" onClick={() => removeBookmark(b.id).then(loadBookmarks)}>
                Remove
              </button>
            </li>
          ))}
          {bookmarks.length === 0 && <li className="muted">No bookmarks yet.</li>}
        </ul>
      </aside>

      <main className="chat-main">
        <div className="message-list">
          {messages.map((m) => (
            <div key={m.id} className={`message message-${m.role}`}>
              <div className="message-content">{m.content}</div>
              <button className="star-button" onClick={() => toggleBookmark(m.id)} title="Bookmark">
                {bookmarkFor(m.id) ? "★" : "☆"}
              </button>
            </div>
          ))}
        </div>

        {pendingAction && (
          <div className="pending-action">
            <p>{pendingAction.summary}</p>
            <button onClick={() => handleConfirm(true)}>Approve</button>
            <button onClick={() => handleConfirm(false)}>Decline</button>
          </div>
        )}

        {error && <p className="form-error">{error}</p>}

        <form className="send-box" onSubmit={handleSend}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message your assistant…"
            disabled={sending}
          />
          <button type="submit" disabled={sending}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
