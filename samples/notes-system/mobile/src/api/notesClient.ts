import Config from "../config";

export interface Note { id: number; title: string; body: string; tags: string[]; isArchived: boolean; updatedUtc: string; }
export interface PagedNotes { items: Note[]; page: number; pageSize: number; total: number; }

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const res = await fetch(`${Config.apiUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  if (res.status === 401) throw new Error("Session expired.");
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error ?? `Request failed (${res.status}).`);
  return body as T;
}

export async function listNotes(page: number, token: string): Promise<PagedNotes> {
  try {
    return await request<PagedNotes>(`/notes?page=${page}&pageSize=25`, {}, token);
  } catch {
    await new Promise((r) => setTimeout(r, 1000));
    return request<PagedNotes>(`/notes?page=${page}&pageSize=25`, {}, token);
  }
}

export const createNote = (title: string, body: string, tags: string[], token: string) =>
  request<Note>("/notes", { method: "POST", body: JSON.stringify({ title, body, tags }) }, token);

export const archiveNote = (id: number, token: string) =>
  request<Note>(`/notes/${id}/archive`, { method: "POST" }, token);
