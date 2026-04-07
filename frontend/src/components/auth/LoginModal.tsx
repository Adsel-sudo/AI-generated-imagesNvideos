"use client";

import { FormEvent, useState } from "react";

export function LoginModal(props: {
  open: boolean;
  loading?: boolean;
  onSubmit: (params: { username: string; password: string }) => Promise<void>;
}) {
  const { open, loading = false, onSubmit } = props;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({ username: username.trim(), password });
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  const disabled = loading || submitting;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-[1px]">
      <form
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_16px_36px_rgba(15,23,42,0.24)]"
        onSubmit={handleSubmit}
      >
        <h2 className="text-base font-semibold text-slate-900">登录工作台</h2>
        <p className="mt-1 text-xs text-slate-500">请输入账号后继续使用。</p>

        <div className="mt-4 space-y-3">
          <input
            type="text"
            autoComplete="username"
            placeholder="用户名"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-200"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            disabled={disabled}
          />
          <input
            type="password"
            autoComplete="current-password"
            placeholder="密码"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-200"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={disabled}
          />
        </div>

        {error ? <div className="mt-3 text-xs text-rose-600">{error}</div> : null}

        <button
          type="submit"
          disabled={disabled}
          className="mt-4 w-full rounded-xl bg-violet-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-violet-300"
        >
          {disabled ? "登录中..." : "登录"}
        </button>
      </form>
    </div>
  );
}
