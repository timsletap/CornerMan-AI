"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { EXP_OPTIONS, STANCE_OPTIONS, WEIGHT_OPTIONS } from "@/lib/fighter-options";
import { formatDate, humanize } from "@/lib/format";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorNote } from "@/components/ui/spinner";

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState({
    full_name: user?.full_name || "",
    stance: user?.stance || "",
    weight_class: user?.weight_class || "",
    experience_level: user?.experience_level || "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const data: Record<string, string> = {};
      if (form.full_name) data.full_name = form.full_name;
      if (form.stance) data.stance = form.stance;
      if (form.weight_class) data.weight_class = form.weight_class;
      if (form.experience_level) data.experience_level = form.experience_level;
      await api.updateMe(data);
      await refreshUser();
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your profile");
    } finally {
      setSaving(false);
    }
  }

  if (!user) return null;

  const tape = [
    ["Stance", user.stance],
    ["Weight class", user.weight_class],
    ["Experience", user.experience_level],
    ["In camp since", formatDate(user.created_at)],
  ] as const;

  return (
    <div className="mx-auto grid max-w-5xl grid-cols-1 gap-6 lg:grid-cols-[0.9fr_1.1fr]">
      {/* Fighter card */}
      <section className="hud-frame self-start border border-line bg-panel/85">
        <div className="border-b border-line p-6 text-center">
          <span className="octagon mx-auto flex h-24 w-24 items-center justify-center bg-blood">
            <span className="display text-6xl text-white">{user.full_name[0]?.toUpperCase()}</span>
          </span>
          <h1 className="display mt-5 text-5xl text-chalk">{user.full_name}</h1>
          <p className="mt-1 text-sm text-mute">{user.email}</p>
          <div className="mt-3 flex justify-center gap-2">
            <Badge color="yellow">{user.tier} tier</Badge>
            <Badge color="zinc">{user.role}</Badge>
          </div>
        </div>
        <p className="eyebrow border-b border-line py-2.5 text-center text-blood">Tale of the tape</p>
        <dl>
          {tape.map(([label, value]) => (
            <div
              key={label}
              className="flex items-baseline justify-between border-b border-line px-6 py-3 last:border-b-0"
            >
              <dt className="eyebrow">{label}</dt>
              <dd className="font-display text-xl font-bold uppercase italic text-chalk">
                {value ? humanize(value) : <span className="text-dim">Not set</span>}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Edit */}
      <Card>
        <CardTitle>Update your card</CardTitle>
        <p className="mt-1 text-sm text-mute">
          Stance and experience shape how your coaching is written.
        </p>
        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          {error && <ErrorNote>{error}</ErrorNote>}
          <Input
            label="Full name"
            value={form.full_name}
            onChange={(e) => update("full_name", e.target.value)}
          />
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Select
              label="Stance"
              options={STANCE_OPTIONS}
              placeholder="Select stance"
              value={form.stance}
              onChange={(e) => update("stance", e.target.value)}
            />
            <Select
              label="Experience"
              options={EXP_OPTIONS}
              placeholder="Select experience"
              value={form.experience_level}
              onChange={(e) => update("experience_level", e.target.value)}
            />
          </div>
          <Select
            label="Weight class"
            options={WEIGHT_OPTIONS}
            placeholder="Select weight class"
            value={form.weight_class}
            onChange={(e) => update("weight_class", e.target.value)}
          />
          <div className="flex items-center gap-4">
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save changes"}
            </Button>
            {saved && (
              <span className="text-sm text-go" role="status">
                Saved
              </span>
            )}
          </div>
        </form>
      </Card>
    </div>
  );
}
