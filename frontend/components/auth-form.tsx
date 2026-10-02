"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, ErrorBanner, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api-client";
import { login, register } from "@/services/auth";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const isRegister = mode === "register";

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      isRegister ? register(email, password, fullName) : login(email, password),
    onSuccess: () => {
      queryClient.clear(); // never show a previous user's cached data
      router.replace("/");
    },
  });

  const error = mutation.error instanceof ApiError ? mutation.error : null;
  // Field-level messages from validation errors (422); anything else shows as a banner
  const hasFieldErrors = !!error && error.details.length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="space-y-4"
      noValidate
    >
      {isRegister && (
        <Field label="Full name" htmlFor="full_name" error={error?.fieldError("full_name")}>
          <Input
            id="full_name"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            autoFocus
          />
        </Field>
      )}
      <Field label="Email" htmlFor="email" error={error?.fieldError("email")}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus={!isRegister}
        />
      </Field>
      <Field
        label="Password"
        htmlFor="password"
        error={error?.fieldError("password")}
        hint={isRegister ? "At least 10 characters." : undefined}
      >
        <Input
          id="password"
          type="password"
          autoComplete={isRegister ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>

      {!hasFieldErrors && <ErrorBanner error={mutation.error} />}

      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? "Please wait…" : isRegister ? "Create account" : "Log in"}
      </Button>

      <p className="text-center text-sm text-muted-foreground">
        {isRegister ? "Already have an account?" : "New to Veluntra?"}{" "}
        <Link
          href={isRegister ? "/login" : "/register"}
          className="font-medium text-accent hover:underline"
        >
          {isRegister ? "Log in" : "Create an account"}
        </Link>
      </p>
    </form>
  );
}
