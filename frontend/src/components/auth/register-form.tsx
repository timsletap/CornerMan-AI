"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { AuthShell } from "@/components/auth/auth-shell";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/spinner";
import { EXP_OPTIONS, STANCE_OPTIONS, WEIGHT_OPTIONS } from "@/lib/fighter-options";

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
      setError(err instanceof Error ? err.message : "Could not create the account");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Join the camp"
      title="Weigh in"
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-chalk underline decoration-blood underline-offset-4 hover:text-blood">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && <ErrorNote>{error}</ErrorNote>}
        <Input
          label="Full name"
          autoComplete="name"
          value={form.full_name}
          onChange={(e) => update("full_name", e.target.value)}
          placeholder="Your name"
          required
        />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={(e) => update("email", e.target.value)}
          placeholder="fighter@example.com"
          required
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          value={form.password}
          onChange={(e) => update("password", e.target.value)}
          placeholder="At least 8 characters"
          minLength={8}
          required
        />

        <fieldset className="space-y-4 border-t border-line pt-5">
          <legend className="eyebrow float-left mb-4 w-full text-chalk">
            Tale of the tape <span className="text-dim">· optional</span>
          </legend>
          <div className="clear-both grid gap-4 sm:grid-cols-2">
            <Select
              label="Stance"
              options={STANCE_OPTIONS}
              placeholder="Select"
              value={form.stance}
              onChange={(e) => update("stance", e.target.value)}
            />
            <Select
              label="Experience"
              options={EXP_OPTIONS}
              placeholder="Select"
              value={form.experience_level}
              onChange={(e) => update("experience_level", e.target.value)}
            />
          </div>
          <Select
            label="Weight class"
            options={WEIGHT_OPTIONS}
            placeholder="Select"
            value={form.weight_class}
            onChange={(e) => update("weight_class", e.target.value)}
          />
          <p className="text-xs text-dim">
            Your stance and level shape how the coaching is written for you.
          </p>
        </fieldset>

        <Button type="submit" size="lg" disabled={loading} className="w-full">
          {loading ? "Creating account..." : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
