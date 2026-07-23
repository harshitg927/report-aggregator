"use client";

import * as React from "react";
import { toast } from "sonner";
import { Loader2, PlugZap, Save, TestTube2, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";

const DEFAULT_FORM = {
  base_url: "",
  token: "",
  group_name: "",
  folder_id: "",
  timeout_seconds: 30,
};

export default function IntegrationsPage() {
  const [form, setForm] = React.useState(DEFAULT_FORM);
  const [hasToken, setHasToken] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    api
      .getIntegrationsConfig()
      .then((body) => {
        if (!alive) return;
        const cfg = body.fossology || {};
        setForm({
          base_url: cfg.base_url || "",
          token: "",
          group_name: cfg.group_name || "",
          folder_id: cfg.folder_id ?? "",
          timeout_seconds: cfg.timeout_seconds || 30,
        });
        setHasToken(Boolean(cfg.has_token));
      })
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : "Failed to load integrations";
        toast.error(msg);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  function update(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function payloadForSave({ clearToken = false } = {}) {
    const payload = {
      base_url: form.base_url,
      group_name: form.group_name,
      folder_id: form.folder_id === "" ? null : Number(form.folder_id),
      timeout_seconds: Number(form.timeout_seconds),
    };
    if (clearToken) payload.token = "";
    else if (form.token.trim()) payload.token = form.token.trim();
    return payload;
  }

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const body = await api.saveIntegrationsConfig(payloadForSave());
      setHasToken(Boolean(body.fossology?.has_token));
      update("token", "");
      toast.success("FOSSology settings saved.");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to save settings";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function clearToken() {
    setSaving(true);
    try {
      const body = await api.saveIntegrationsConfig(payloadForSave({ clearToken: true }));
      setHasToken(Boolean(body.fossology?.has_token));
      update("token", "");
      toast.success("FOSSology token cleared.");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to clear token";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setTesting(true);
    try {
      const result = await api.testFossologyConnection();
      if (result.ok) toast.success(result.message || "Connection successful.");
      else toast.error(result.error || "Connection failed.");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Connection failed";
      toast.error(msg);
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="Integrations"
        description="Configure FOSSology for importing existing upload reports."
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <PlugZap className="h-4 w-4" /> FOSSology
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading settings
            </div>
          ) : (
            <form onSubmit={save} className="grid gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor="base_url">Base URL</Label>
                <Input
                  id="base_url"
                  value={form.base_url}
                  onChange={(e) => update("base_url", e.target.value)}
                  placeholder="https://fossology.example"
                />
              </div>

              <div className="grid gap-1.5">
                <Label htmlFor="token">Token or env reference</Label>
                <Input
                  id="token"
                  value={form.token}
                  onChange={(e) => update("token", e.target.value)}
                  placeholder={hasToken ? "Saved token present; leave blank to keep it" : "token or env:FOSSOLOGY_TOKEN"}
                />
                {hasToken && <p className="text-xs text-muted-foreground">A token is saved server-side.</p>}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor="group_name">Group</Label>
                  <Input
                    id="group_name"
                    value={form.group_name}
                    onChange={(e) => update("group_name", e.target.value)}
                    placeholder="fossy"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="folder_id">Default folder ID</Label>
                  <Input
                    id="folder_id"
                    type="number"
                    min="1"
                    value={form.folder_id}
                    onChange={(e) => update("folder_id", e.target.value)}
                  />
                </div>
              </div>

              <div className="grid gap-1.5 sm:max-w-xs">
                <Label htmlFor="timeout_seconds">Timeout seconds</Label>
                <Input
                  id="timeout_seconds"
                  type="number"
                  min="1"
                  value={form.timeout_seconds}
                  onChange={(e) => update("timeout_seconds", e.target.value)}
                />
              </div>

              <div className="flex flex-wrap gap-2 pt-2">
                <Button type="submit" disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save
                </Button>
                <Button type="button" variant="secondary" onClick={testConnection} disabled={testing || saving}>
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube2 className="h-4 w-4" />}
                  Test connection
                </Button>
                {hasToken && (
                  <Button type="button" variant="ghost" onClick={clearToken} disabled={saving}>
                    <Trash2 className="h-4 w-4" /> Clear token
                  </Button>
                )}
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
