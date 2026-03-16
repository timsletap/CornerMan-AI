"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const STANCE_OPTIONS = [
  { value: "orthodox", label: "Orthodox" },
  { value: "southpaw", label: "Southpaw" },
  { value: "switch", label: "Switch" },
];

const WEIGHT_OPTIONS = [
  { value: "strawweight", label: "Strawweight" },
  { value: "flyweight", label: "Flyweight" },
  { value: "bantamweight", label: "Bantamweight" },
  { value: "featherweight", label: "Featherweight" },
  { value: "lightweight", label: "Lightweight" },
  { value: "welterweight", label: "Welterweight" },
  { value: "middleweight", label: "Middleweight" },
  { value: "light_heavyweight", label: "Light Heavyweight" },
  { value: "heavyweight", label: "Heavyweight" },
];

const EXP_OPTIONS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
  { value: "pro", label: "Pro" },
];

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

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const data: Record<string, string> = {};
      if (form.full_name) data.full_name = form.full_name;
      if (form.stance) data.stance = form.stance;
      if (form.weight_class) data.weight_class = form.weight_class;
      if (form.experience_level) data.experience_level = form.experience_level;
      await api.updateMe(data);
      await refreshUser();
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  if (!user) return null;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Profile</h1>

      <Card>
        <div className="flex items-center gap-4 mb-4">
          <div className="h-16 w-16 rounded-full bg-red-600 flex items-center justify-center text-2xl font-bold text-white">
            {user.full_name[0]?.toUpperCase()}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">{user.full_name}</h2>
            <p className="text-sm text-zinc-400">{user.email}</p>
            <div className="flex gap-2 mt-1">
              <Badge color="blue">{user.tier}</Badge>
              <Badge color="zinc">{user.role}</Badge>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle>Edit Profile</CardTitle>
        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          <Input
            label="Full Name"
            value={form.full_name}
            onChange={(e) => update("full_name", e.target.value)}
          />
          <Select
            label="Stance"
            options={STANCE_OPTIONS}
            placeholder="Select stance"
            value={form.stance}
            onChange={(e) => update("stance", e.target.value)}
          />
          <Select
            label="Weight Class"
            options={WEIGHT_OPTIONS}
            placeholder="Select weight class"
            value={form.weight_class}
            onChange={(e) => update("weight_class", e.target.value)}
          />
          <Select
            label="Experience Level"
            options={EXP_OPTIONS}
            placeholder="Select experience"
            value={form.experience_level}
            onChange={(e) => update("experience_level", e.target.value)}
          />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </Button>
            {saved && <span className="text-sm text-green-400">Saved!</span>}
          </div>
        </form>
      </Card>
    </div>
  );
}
