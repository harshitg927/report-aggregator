/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Header } from "@/components/header";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("app shell", () => {
  it("renders the brand and new-merge action", () => {
    render(<Header />);
    expect(screen.getByText("Report Aggregator")).toBeInTheDocument();
    expect(screen.getByText("New Merge")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });
});
