/** Minimal fetch-based HTTP client.

Stays thin and dependency-free. Adds a timeout, friendly network/error handling,
and consistent `ApiError` types so pages can render useful messages without
touching fetch directly.
*/

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
const DEFAULT_TIMEOUT_MS = 30000;

/** Thrown for every HTTP / network / malformed-response failure. */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** True when the backend could not be reached at all (network / timeout). */
export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong while talking to the interview service.";
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      signal: controller.signal,
      ...options,
    });
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === "AbortError";
    throw new ApiError(
      aborted
        ? "The interview service is taking too long to respond. Try again."
        : "Unable to reach the interview service. Check that the backend is running and try again.",
      0,
      "network_error"
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let code: string | undefined;
    try {
      const body = await response.json();
      if (body?.error?.message) {
        message = body.error.message;
        code = body.error.code;
      } else if (body?.detail) {
        message = Array.isArray(body.detail)
          ? "The interview service rejected the request."
          : String(body.detail);
      }
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(message, response.status, code);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "The interview service returned an unexpected response.",
      response.status,
      "malformed_response"
    );
  }
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export { describeError };
