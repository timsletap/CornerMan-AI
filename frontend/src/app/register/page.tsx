"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { RegisterForm } from "@/components/auth/register-form";
import { LoadingBlock } from "@/components/ui/spinner";

export default function RegisterPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [user, loading, router]);

  if (loading) return <LoadingBlock fullScreen />;

  return <RegisterForm />;
}
