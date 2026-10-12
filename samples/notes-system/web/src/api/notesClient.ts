export interface Note { id: number; title: string; body: string; tags: string[]; isArchived: boolean; updatedUtc: string; }
export interface PagedNotes { items: Note[]; page: number; pageSize: number; total: number; }

const BASE = import.meta.env.VITE_API_URL ?? "/api";

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  if (res.status === 401) throw new Error("Please sign in again.");
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.errors?.join(" ") ?? body?.error ?? `Request failed (${res.status}).`);
  return body as T;
}

export async function listNotes(page: number, token: string, archived = false): Promise<PagedNotes> {
  // one retry for flaky networks, but never for auth or validation failures
  try {
    return await request<PagedNotes>(`/notes?page=${page}&pageSize=20&archived=${archived}`, {}, token);
  } catch (e) {
    if (e instanceof Error && e.message === "Please sign in again.") throw e;
    await new Promise((r) => setTimeout(r, 400));
    return request<PagedNotes>(`/notes?page=${page}&pageSize=20&archived=${archived}`, {}, token);
  }
}

export const createNote = (title: string, body: string, tags: string[], token: string) =>
  request<Note>("/notes", { method: "POST", body: JSON.stringify({ title, body, tags }) }, token);

export const archiveNote = (id: number, token: string) =>
  request<Note>(`/notes/${id}/archive`, { method: "POST" }, token);
