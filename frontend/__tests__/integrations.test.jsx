import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock("sonner", () => ({
  toast: { error: (...a) => toastError(...a), success: (...a) => toastSuccess(...a) },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getIntegrationsConfig: vi.fn(),
    saveIntegrationsConfig: vi.fn(),
    testFossologyConnection: vi.fn(),
  },
}));

import { api } from "@/lib/api";
import IntegrationsPage from "@/app/integrations/page";

describe("integrations page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getIntegrationsConfig.mockResolvedValue({
      fossology: {
        configured: true,
        base_url: "https://fossology.example",
        group_name: "fossy",
        folder_id: 7,
        timeout_seconds: 30,
        has_token: true,
      },
    });
    api.saveIntegrationsConfig.mockResolvedValue({ fossology: { has_token: true } });
    api.testFossologyConnection.mockResolvedValue({ ok: true, message: "Connection successful" });
  });

  it("saves config without displaying returned token values", async () => {
    render(<IntegrationsPage />);
    await screen.findByDisplayValue("https://fossology.example");

    await userEvent.clear(screen.getByLabelText(/token or env reference/i));
    await userEvent.type(screen.getByLabelText(/token or env reference/i), "env:FOSSOLOGY_TOKEN");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(api.saveIntegrationsConfig).toHaveBeenCalled());
    expect(screen.queryByDisplayValue("env:FOSSOLOGY_TOKEN")).not.toBeInTheDocument();
    expect(toastSuccess).toHaveBeenCalled();
  });

  it("tests the saved FOSSology connection", async () => {
    render(<IntegrationsPage />);
    await screen.findByDisplayValue("https://fossology.example");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));

    await waitFor(() => expect(api.testFossologyConnection).toHaveBeenCalled());
    expect(toastSuccess).toHaveBeenCalledWith("Connection successful");
  });
});
