// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0 DOM fix: the shared Table must never emit `<tr>` as a child of `<tr>`,
// regardless of which header pattern a consumer uses.
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./index";

function assertNoNestedRows(container: HTMLElement) {
  const rows = container.querySelectorAll("tr");
  rows.forEach((tr) => {
    expect(tr.querySelector("tr")).toBeNull();
  });
  // A <tr> must never have a parent that is also a <tr>.
  rows.forEach((tr) => {
    expect(tr.parentElement?.tagName.toLowerCase()).not.toBe("tr");
  });
}

describe("shared Table DOM structure", () => {
  it("supports header cells passed directly (no nested tr)", () => {
    const { container } = render(
      <Table>
        <TableHeader>
          <TableHead>Symbol</TableHead>
          <TableHead>Verdict</TableHead>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>AAPL</TableCell>
            <TableCell>ENTRY</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    );
    assertNoNestedRows(container);
    // exactly one header tr + one body tr
    expect(container.querySelectorAll("thead tr").length).toBe(1);
  });

  it("supports header cells wrapped in TableRow (no nested tr)", () => {
    const { container } = render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Symbol</TableHead>
            <TableHead>Verdict</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>AAPL</TableCell>
            <TableCell>ENTRY</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    );
    assertNoNestedRows(container);
    expect(container.querySelectorAll("thead tr").length).toBe(1);
  });
});
