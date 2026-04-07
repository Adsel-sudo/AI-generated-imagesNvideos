const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim().replace(/\/$/, "");

type HttpMethod = "GET" | "POST";

interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
}

function getErrorMessage(response: Response, rawText: string, parsed: unknown): string {
  if (typeof parsed === "string" && parsed.trim()) {
    return parsed.trim();
  }

  const parsedError =
    parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;

  return (
    (typeof parsedError?.detail === "string" && parsedError.detail) ||
    (typeof parsedError?.message === "string" && parsedError.message) ||
    (typeof parsedError?.error === "string" && parsedError.error) ||
    rawText.trim() ||
    `Request failed with status ${response.status}${response.statusText ? ` ${response.statusText}` : ""}`
  );
}

function getRequestUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

function parseResponseBody(rawText: string): unknown {
  if (!rawText) {
    return null;
  }

  try {
    return JSON.parse(rawText);
  } catch {
    return rawText;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body } = options;

  const response = await fetch(getRequestUrl(path), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });

  const rawText = await response.text();
  const parsed = parseResponseBody(rawText);

  if (!response.ok) {
    throw new Error(getErrorMessage(response, rawText, parsed));
  }

  if (parsed !== null) {
    return parsed as T;
  }

  return rawText as T;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
