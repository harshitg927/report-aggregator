/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

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
  api: {
    merge: vi.fn(),
    getIntegrationsConfig: vi.fn(),
    listFossologyFolders: vi.fn(),
    listFossologyUploads: vi.fn(),
    mergeFossologyUploads: vi.fn(),
    getIntegrationJob: vi.fn(),
  },
}));

import { api } from "@/lib/api";
import MergePage from "@/app/merge/page";

function makeFile(name) {
  return new File(["content-" + name], name, { type: "application/json" });
}

describe("merge wizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: false } });
    api.listFossologyFolders.mockResolvedValue({ folders: [] });
    api.listFossologyUploads.mockResolvedValue({ uploads: [], total_pages: "1" });
  });

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

  it("shows FOSSology upload metadata before selection", async () => {
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: true } });
    api.listFossologyFolders.mockResolvedValue({
      folders: [{ id: 3, name: "Third Party" }],
    });
    api.listFossologyUploads.mockResolvedValue({
      uploads: [
        {
          id: 1,
          uploadName: "pkg-a.zip",
          folderName: "Third Party",
          assignee: 42,
          uploadDate: "2026-07-14T10:30:00Z",
          description: "Initial compliance import",
          status: "open",
          hash: { sha1: "abcdef123456", size: 1536 },
        },
        { id: 2, uploadName: "pkg-b.zip" },
      ],
      total_pages: "1",
    });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await screen.findByText("pkg-a.zip");

    expect(screen.getByText("ID: 1")).toBeInTheDocument();
    expect(screen.getByText("Folder: Third Party")).toBeInTheDocument();
    expect(screen.getByText("Assignee: 42")).toBeInTheDocument();
    expect(screen.getByText("SHA-1: abcdef123456")).toBeInTheDocument();
    expect(screen.getByText("Size: 1.5 KB")).toBeInTheDocument();
    expect(screen.getByText("Initial compliance import")).toBeInTheDocument();
    expect(screen.getByText("open")).toBeInTheDocument();
  });

  it("validates FOSSology upload selection", async () => {
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: true } });
    api.listFossologyFolders.mockResolvedValue({ folders: [{ id: 1, name: "Main" }] });
    api.listFossologyUploads.mockResolvedValue({
      uploads: [{ id: 1, uploadName: "pkg-a" }, { id: 2, uploadName: "pkg-b" }],
      total_pages: "1",
    });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await screen.findByText("pkg-a");
    await userEvent.click(screen.getByRole("button", { name: /merge selected uploads/i }));

    expect(toastError).toHaveBeenCalled();
    expect(api.mergeFossologyUploads).not.toHaveBeenCalled();
  });

  it("polls a successful FOSSology job and redirects", async () => {
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: true } });
    api.listFossologyFolders.mockResolvedValue({ folders: [{ id: 1, name: "Main" }] });
    api.listFossologyUploads.mockResolvedValue({
      uploads: [{ id: 1, uploadName: "pkg-a" }, { id: 2, uploadName: "pkg-b" }],
      total_pages: "1",
    });
    api.mergeFossologyUploads.mockResolvedValue({ job_id: "job-1", status: "queued" });
    api.getIntegrationJob.mockResolvedValue({
      status: "succeeded",
      completed: 2,
      total: 2,
      aggregate_id: "agg-1",
    });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /select pkg-a/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /select pkg-b/i }));
    await userEvent.click(screen.getByRole("button", { name: /merge selected uploads/i }));

    await waitFor(() => expect(api.mergeFossologyUploads).toHaveBeenCalledWith({
      upload_ids: [1, 2],
      report_format: "cyclonedx",
    }));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/reports/agg-1"));
  });

  it("loads folders and reloads uploads when folder changes", async () => {
    api.getIntegrationsConfig.mockResolvedValue({
      fossology: { configured: true, folder_id: 1 },
    });
    api.listFossologyFolders.mockResolvedValue({
      folders: [
        { id: 1, name: "Main" },
        { id: 2, name: "Archive" },
      ],
    });
    api.listFossologyUploads.mockResolvedValue({ uploads: [], total_pages: "1" });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await waitFor(() => expect(api.listFossologyFolders).toHaveBeenCalled());
    await waitFor(() =>
      expect(api.listFossologyUploads).toHaveBeenCalledWith(
        expect.objectContaining({ folder_id: 1, page: 1, limit: 50 })
      )
    );

    await userEvent.click(screen.getByLabelText(/^folder$/i));
    await userEvent.click(screen.getByRole("button", { name: /archive \(id: 2\)/i }));
    await waitFor(() =>
      expect(api.listFossologyUploads).toHaveBeenLastCalledWith(
        expect.objectContaining({ folder_id: 2, page: 1 })
      )
    );
  });

  it("filters folders in the searchable dropdown", async () => {
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: true } });
    api.listFossologyFolders.mockResolvedValue({
      folders: [
        { id: 1, name: "Main" },
        { id: 2, name: "Archive" },
        { id: 3, name: "Third Party" },
      ],
    });
    api.listFossologyUploads.mockResolvedValue({ uploads: [], total_pages: "1" });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await waitFor(() => expect(api.listFossologyFolders).toHaveBeenCalled());

    await userEvent.click(screen.getByLabelText(/^folder$/i));
    await userEvent.type(screen.getByLabelText(/search options/i), "arch");
    expect(screen.getByRole("button", { name: /archive \(id: 2\)/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /main \(id: 1\)/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /third party \(id: 3\)/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /archive \(id: 2\)/i }));
    await waitFor(() =>
      expect(api.listFossologyUploads).toHaveBeenLastCalledWith(
        expect.objectContaining({ folder_id: 2, page: 1 })
      )
    );
  });

  it("paginates uploads with next page", async () => {
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: true } });
    api.listFossologyFolders.mockResolvedValue({ folders: [{ id: 1, name: "Main" }] });
    api.listFossologyUploads
      .mockResolvedValueOnce({
        uploads: [{ id: 1, uploadName: "pkg-a" }],
        total_pages: "3",
      })
      .mockResolvedValueOnce({
        uploads: [{ id: 2, uploadName: "pkg-b" }],
        total_pages: "3",
      });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await screen.findByText("pkg-a");
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() =>
      expect(api.listFossologyUploads).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, limit: 50 })
      )
    );
    await screen.findByText("pkg-b");
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("resets to page 1 when page size changes", async () => {
    api.getIntegrationsConfig.mockResolvedValue({ fossology: { configured: true } });
    api.listFossologyFolders.mockResolvedValue({ folders: [{ id: 1, name: "Main" }] });
    api.listFossologyUploads.mockResolvedValue({
      uploads: [{ id: 1, uploadName: "pkg-a" }],
      total_pages: "2",
    });
    render(<MergePage />);

    await userEvent.click(screen.getByRole("button", { name: /fossology uploads/i }));
    await screen.findByText("pkg-a");
    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() =>
      expect(api.listFossologyUploads).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );

    await userEvent.selectOptions(screen.getByLabelText(/page size/i), "25");
    await waitFor(() =>
      expect(api.listFossologyUploads).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, limit: 25 })
      )
    );
  });

});
