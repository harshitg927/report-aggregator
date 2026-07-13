import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), refresh: vi.fn() }),
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock("sonner", () => ({
  toast: { error: (...a) => toastError(...a), success: (...a) => toastSuccess(...a) },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: { merge: vi.fn() },
}));

import { api } from "@/lib/api";
import MergePage from "@/app/merge/page";

function makeFile(name) {
  return new File(["content-" + name], name, { type: "application/json" });
}

describe("merge wizard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("rejects fewer than two files", async () => {
    render(<MergePage />);
    await userEvent.click(screen.getByRole("button", { name: /merge reports/i }));
    expect(toastError).toHaveBeenCalled();
    expect(api.merge).not.toHaveBeenCalled();
  });

  it("merges two files and redirects to the new report", async () => {
    api.merge.mockResolvedValue({ aggregate_id: "new-agg-id" });
    render(<MergePage />);

    const input = screen.getByLabelText(/report files/i);
    await userEvent.upload(input, [makeFile("a.json"), makeFile("b.json")]);

    await userEvent.click(screen.getByRole("button", { name: /merge reports/i }));

    await waitFor(() => expect(api.merge).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith("/reports/new-agg-id")
    );
  });

  it("shows an error toast when the API rejects the merge", async () => {
    api.merge.mockRejectedValue(new Error("Format mismatch"));
    render(<MergePage />);

    const input = screen.getByLabelText(/report files/i);
    await userEvent.upload(input, [makeFile("a.json"), makeFile("b.json")]);
    await userEvent.click(screen.getByRole("button", { name: /merge reports/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(mockPush).not.toHaveBeenCalled();
  });
});
