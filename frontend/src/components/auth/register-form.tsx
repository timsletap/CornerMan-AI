"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

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

export function RegisterForm() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    stance: "",
    weight_class: "",
    experience_level: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data: Record<string, string> = {
        email: form.email,
        password: form.password,
        full_name: form.full_name,
      };
      if (form.stance) data.stance = form.stance;
      if (form.weight_class) data.weight_class = form.weight_class;
      if (form.experience_level) data.experience_level = form.experience_level;
      await register(data as Parameters<typeof register>[0]);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md mx-auto">
      <div className="text-center mb-6">
        <div className="h-12 w-12 rounded-xl bg-red-600 flex items-center justify-center font-bold text-white text-xl mx-auto mb-3">
          CM
        </div>
        <h1 className="text-2xl font-bold text-white">Create Account</h1>
        <p className="text-zinc-400 text-sm mt-1">Set up your fighter profile</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg bg-red-900/30 border border-red-800 p-3 text-sm text-red-400">
            {error}
          </div>
        )}
        <Input
          label="Full Name"
          value={form.full_name}
          onChange={(e) => update("full_name", e.target.value)}
          placeholder="Your name"
          required
        />
        <Input
          label="Email"
          type="email"
          value={form.email}
          onChange={(e) => update("email", e.target.value)}
          placeholder="fighter@example.com"
          required
        />
        <Input
          label="Password"
          type="password"
          value={form.password}
          onChange={(e) => update("password", e.target.value)}
          placeholder="Min 8 characters"
          minLength={8}
          required
        />
        <Select
          label="Stance"
          options={STANCE_OPTIONS}
          placeholder="Select stance (optional)"
          value={form.stance}
          onChange={(e) => update("stance", e.target.value)}
        />
        <Select
          label="Weight Class"
          options={WEIGHT_OPTIONS}
          placeholder="Select weight class (optional)"
          value={form.weight_class}
          onChange={(e) => update("weight_class", e.target.value)}
        />
        <Select
          label="Experience Level"
          options={EXP_OPTIONS}
          placeholder="Select experience (optional)"
          value={form.experience_level}
          onChange={(e) => update("experience_level", e.target.value)}
        />
        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Creating account..." : "Create Account"}
        </Button>
      </form>

      <p className="text-center text-sm text-zinc-400 mt-4">
        Already have an account?{" "}
        <Link href="/login" className="text-red-400 hover:text-red-300">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
