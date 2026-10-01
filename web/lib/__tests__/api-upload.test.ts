import { afterEach, describe, expect, it, vi } from "vitest";
import { API_URL, checkApiReachable, uploadDocument } from "@/lib/api";
import { ApiError, ConnectionError, FileReadError } from "@/lib/errors";

afterEach(() => vi.unstubAllGlobals());

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const pdf = () => new File(["%PDF-1.4 cv"], "cv.pdf", { type: "application/pdf" });

describe("uploadDocument", () => {
  it("posts the file as multipart form data to the configured API's /documents", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const form = init?.body as FormData;
      const sent = form.get("file") as File;
      expect(sent.name).toBe("cv.pdf");
      expect(await sent.text()).toBe("%PDF-1.4 cv");
      return json(201, { id: "d1", status: "received", created: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await uploadDocument(pdf());
    expect(result).toEqual({ id: "d1", status: "received", created: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/documents`);
    expect(init?.method).toBe("POST");
  });

  it("uses the localhost API address a host browser can actually reach, never a container hostname", () => {
    expect(API_URL).toMatch(/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/);
  });

  it("reports an unanswered request as ConnectionError naming the API address", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await uploadDocument(pdf()).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ConnectionError);
    expect((error as ConnectionError).message).toContain(API_URL);
  });

  it("keeps a server rejection as an ApiError, not a connection failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(415, { detail: "unsupported_file" })));
    const error = await uploadDocument(pdf()).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(415);
  });

  it("reports an unreadable file as FileReadError and sends nothing", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const broken = pdf();
    Object.defineProperty(broken, "arrayBuffer", { value: () => Promise.reject(new DOMException("gone", "NotReadableError")) });
    await expect(uploadDocument(broken)).rejects.toBeInstanceOf(FileReadError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("checkApiReachable", () => {
  it("resolves when the health check answers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, { status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(checkApiReachable()).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_URL}/health`);
  });

  it("rejects with ConnectionError when nothing answers, and when the answer is not healthy", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(checkApiReachable()).rejects.toBeInstanceOf(ConnectionError);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(503, {})));
    await expect(checkApiReachable()).rejects.toBeInstanceOf(ConnectionError);
  });
});
