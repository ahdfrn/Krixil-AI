import { apiFetch } from "@/lib/api/client";

export interface WorkspaceEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number | null;
}

export interface WorkspaceFile {
  path: string;
  content: string;
}

export async function listWorkspaceFiles(dir: string = "."): Promise<WorkspaceEntry[]> {
  return apiFetch<WorkspaceEntry[]>(`/workspace/files?path=${encodeURIComponent(dir)}`);
}

export async function getWorkspaceFileContent(path: string): Promise<WorkspaceFile> {
  return apiFetch<WorkspaceFile>(`/workspace/files/content?path=${encodeURIComponent(path)}`);
}

export async function uploadWorkspaceFile(path: string, file: File): Promise<WorkspaceFile> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<WorkspaceFile>(
    `/workspace/files?path=${encodeURIComponent(path)}`,
    { method: "POST", body: formData },
  );
}

export async function deleteWorkspaceFile(path: string): Promise<void> {
  return apiFetch<void>(`/workspace/files?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  });
}
