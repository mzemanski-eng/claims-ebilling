"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, getMe } from "@/lib/api";
import { setToken, setRole, setUserInfo } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const tokenRes = await login(email, password);
      setToken(tokenRes.access_token);
      setRole(tokenRes.role);

      const user = await getMe();
      setUserInfo(user);

      // Redirect by role
      if (tokenRes.role === "SUPPLIER") {
        router.push("/supplier/invoices");
      } else if (
        tokenRes.role === "CARRIER_ADMIN" ||
        tokenRes.role === "CARRIER_REVIEWER"
      ) {
        router.push("/carrier/queue");
      } else {
        router.push("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-blue-700">Claims eBilling</h1>
          <p className="mt-1 text-sm text-gray-500">
            Sign in to your account
          </p>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          className="rounded-xl border bg-white px-8 py-8 shadow-sm space-y-5"
        >
          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <Input
            id="email"
            label="Email address"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <Input
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <Button
            type="submit"
            className="w-full"
            loading={loading}
            size="lg"
          >
            Sign in
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-gray-400">
          Claims ALAE eBilling Platform · v1.0
        </p>
      </div>
    </div>
  );
}
