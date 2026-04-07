import { getApiBaseUrl } from "@/src/lib/api/client";

export type UploadFileResponse = {
  file_id: string;
  file_name?: string;
  file_path?: string;
  mime_type?: string;
  url?: string;
};

const parseJsonSafe = async (response: Response) => {
  const raw = await response.text();
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
};

export async function uploadFile(file: File): Promise<UploadFileResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${getApiBaseUrl()}/api/files`, {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  const json = await parseJsonSafe(response);

  if (!response.ok) {
    const message =
      (typeof json?.detail === "string" && json.detail) ||
      (typeof json?.message === "string" && json.message) ||
      "文件上传失败，请稍后重试。";
    throw new Error(message);
  }

  const fileId =
    (typeof json?.file_id === "string" && json.file_id) ||
    (typeof json?.id === "string" && json.id) ||
    (json?.file && typeof json.file === "object" && typeof (json.file as Record<string, unknown>).id === "string"
      ? ((json.file as Record<string, unknown>).id as string)
      : undefined);

  if (!fileId) {
    throw new Error("上传成功但未返回文件ID，请联系管理员。");
  }

  return {
    file_id: fileId,
    file_name: typeof json?.file_name === "string" ? json.file_name : file.name,
    file_path: typeof json?.file_path === "string" ? json.file_path : undefined,
    mime_type: typeof json?.mime_type === "string" ? json.mime_type : file.type,
    url: typeof json?.url === "string" ? json.url : undefined,
  };
}
