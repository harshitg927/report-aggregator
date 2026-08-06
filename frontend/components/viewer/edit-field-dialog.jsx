/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

/**
 * Coerce the edited text back to the node's original primitive type so the
 * rendered report keeps valid types.
 */
function coerceValue(text, valueType) {
  if (valueType === "int") {
    const n = parseInt(text, 10);
    return Number.isNaN(n) ? text : n;
  }
  if (valueType === "float") {
    const n = parseFloat(text);
    return Number.isNaN(n) ? text : n;
  }
  if (valueType === "bool") {
    return text === "true";
  }
  return text;
}

export function EditFieldDialog({ node, open, onClose, onSubmit, submitting }) {
  const [value, setValue] = React.useState("");
  const [who, setWho] = React.useState("");
  const [reason, setReason] = React.useState("");

  React.useEffect(() => {
    if (node) {
      setValue(node.value == null ? "" : String(node.value));
      setReason("");
    }
  }, [node]);

  if (!node) return null;

  function submit(e) {
    e.preventDefault();
    onSubmit({
      op: "replace",
      path: node.path,
      value: coerceValue(value, node.valueType),
      who: who.trim() || "user",
      reason: reason.trim(),
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Edit field"
      description={node.path}
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="edit-value">Value</Label>
          {node.valueType === "bool" ? (
            <Select
              id="edit-value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </Select>
          ) : (
            <Input
              id="edit-value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
            />
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="edit-who">Who</Label>
          <Input
            id="edit-who"
            placeholder="you@example.com"
            value={who}
            onChange={(e) => setWho(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="edit-reason">Reason (optional)</Label>
          <Input
            id="edit-reason"
            placeholder="Why this change?"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save edit"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
