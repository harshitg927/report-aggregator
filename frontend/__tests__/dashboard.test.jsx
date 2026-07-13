import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: { listReports: vi.fn() },
}));

import { api } from "@/lib/api";
import DashboardPage from "@/app/page";

const SAMPLE_REPORTS = {
  reports: [
    {
      aggregate_id: "abcd1234efgh",
      format: "cyclonedx",
      created_at: "2026-06-22T00:00:00Z",
      output_filename: "merged.json",
      inputs: [
        { source_id: "zlib132", filename: "CYCLONEDX_zlib132.zip.json", input_index: 0 },
        { source_id: "fckeditor", filename: "CYCLONEDX_fckeditor.zip.json", input_index: 1 },
      ],
      counts: { inputs: 2, conflicts: 1, edits: 3 },
    },
    {
      aggregate_id: "clixml9999aaaa",
      format: "clixml",
      created_at: "2026-06-23T00:00:00Z",
      output_filename: "merged.xml",
      inputs: [
        { source_id: "zlib", filename: "CLIXML_zlib132.zip.xml", input_index: 0 },
        { source_id: "fck", filename: "CLIXML_fckeditor.zip.xml", input_index: 1 },
      ],
      counts: { inputs: 2, conflicts: 0, edits: 0 },
    },
  ],
};

describe("dashboard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders report cards from the API", async () => {
    api.listReports.mockResolvedValue({ reports: [SAMPLE_REPORTS.reports[0]] });

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("abcd1234")).toBeInTheDocument()
    );
    expect(screen.getAllByText("CycloneDX 1.4").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no reports", async () => {
    api.listReports.mockResolvedValue({ reports: [] });
    render(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByText(/No merged reports yet/i)).toBeInTheDocument()
    );
  });

  it("filters reports by search text", async () => {
    api.listReports.mockResolvedValue(SAMPLE_REPORTS);
    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("clixml99")).toBeInTheDocument()
    );

    await userEvent.type(screen.getByLabelText(/search/i), "clixml_zlib");

    expect(screen.queryByText("abcd1234")).not.toBeInTheDocument();
    expect(screen.getByText("clixml99")).toBeInTheDocument();
  });

  it("filters reports by format and status", async () => {
    api.listReports.mockResolvedValue(SAMPLE_REPORTS);
    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("abcd1234")).toBeInTheDocument()
    );

    await userEvent.selectOptions(screen.getByLabelText(/^format$/i), "clixml");
    expect(screen.queryByText("abcd1234")).not.toBeInTheDocument();
    expect(screen.getByText("clixml99")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText(/^format$/i), "");
    await userEvent.selectOptions(screen.getByLabelText(/^filter$/i), "conflicts");
    expect(screen.getByText("abcd1234")).toBeInTheDocument();
    expect(screen.queryByText("clixml99")).not.toBeInTheDocument();
  });

  it("links conflicts and edits cells to report pages", async () => {
    api.listReports.mockResolvedValue({ reports: [SAMPLE_REPORTS.reports[0]] });
    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("abcd1234")).toBeInTheDocument()
    );

    expect(
      screen.getByRole("link", { name: /view 1 conflicts for report abcd1234/i })
    ).toHaveAttribute("href", "/reports/abcd1234efgh/conflicts");
    expect(
      screen.getByRole("link", { name: /view 3 edits for report abcd1234/i })
    ).toHaveAttribute("href", "/reports/abcd1234efgh/history");
  });

  it("shows merged input files on hover", async () => {
    api.listReports.mockResolvedValue({ reports: [SAMPLE_REPORTS.reports[0]] });
    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByLabelText(/view 2 merged inputs/i)).toBeInTheDocument()
    );

    await userEvent.hover(screen.getByLabelText(/view 2 merged inputs/i));
    await waitFor(() =>
      expect(screen.getByText("CYCLONEDX_zlib132.zip.json")).toBeInTheDocument()
    );
    expect(screen.getByText("CYCLONEDX_fckeditor.zip.json")).toBeInTheDocument();
    expect(screen.getAllByText(/^Input \d$/)).toHaveLength(2);
  });
});
