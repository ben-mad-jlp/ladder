import { useCallback, useEffect, useState } from "react";
import { archiveNote, createNote, listNotes, type Note } from "../api/notesClient";

export function useNotes(token: string) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (p: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await listNotes(p, token);
      setNotes((prev) => (p === 1 ? res.items : [...prev, ...res.items]));
      setTotal(res.total);
      setPage(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(1); }, [load]);

  const add = async (title: string, body: string, tagText: string) => {
    const tags = tagText.split(",").map((t) => t.trim()).filter(Boolean);
    const note = await createNote(title, body, tags, token);
    setNotes((prev) => [note, ...prev]);
    setTotal((t) => t + 1);
  };

  const archive = async (id: number) => {
    // optimistic: hide it now, put it back if the server refuses
    const before = notes;
    setNotes((prev) => prev.filter((n) => n.id !== id));
    try { await archiveNote(id, token); setTotal((t) => t - 1); }
    catch (e) { setNotes(before); setError(e instanceof Error ? e.message : "Could not archive the note."); }
  };

  return { notes, total, error, loading, hasMore: notes.length < total, loadMore: () => load(page + 1), reload: () => load(1), add, archive };
}
