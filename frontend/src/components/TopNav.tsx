"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const isActive =
    href === "/"
      ? pathname === "/" || pathname.startsWith("/image")
      : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      aria-current={isActive ? "page" : undefined}
      className={[
        "inline-flex items-center rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
        isActive
          ? "border border-violet-200/90 bg-gradient-to-b from-violet-100 to-violet-50 text-violet-700 shadow-[0_2px_10px_rgba(124,58,237,0.18)]"
          : "border border-transparent text-slate-600 hover:border-slate-200/90 hover:bg-white/80 hover:text-slate-900",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function TopNav() {
  return (
    <header className="sticky top-0 z-20 border-b border-violet-100/60 bg-gradient-to-r from-slate-100/90 via-slate-100/85 to-violet-100/60 shadow-[0_8px_24px_rgba(15,23,42,0.08)] backdrop-blur supports-[backdrop-filter]:bg-slate-100/70">
      <div className="mx-auto flex w-full max-w-[1520px] items-center justify-between px-3 py-2 sm:px-4">
        <nav className="flex items-center gap-1.5 rounded-xl border border-violet-100/70 bg-white/80 p-1.5 shadow-[0_10px_24px_rgba(76,29,149,0.08)] ring-1 ring-white/70 backdrop-blur">
          <NavItem href="/" label="AI图片" />
          <NavItem href="/video" label="AI视频" />
        </nav>
      </div>
    </header>
  );
}
