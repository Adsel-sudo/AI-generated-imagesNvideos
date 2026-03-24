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
        "inline-flex items-center rounded-lg px-3 py-1.5 text-sm font-medium transition",
        isActive
          ? "border border-violet-200 bg-violet-100/80 text-violet-700 shadow-sm"
          : "border border-transparent text-slate-600 hover:border-slate-200 hover:bg-white/80 hover:text-slate-900",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function TopNav() {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-slate-100/70 backdrop-blur supports-[backdrop-filter]:bg-slate-100/55">
      <div className="mx-auto flex w-full max-w-[1520px] items-center justify-between px-3 py-2 sm:px-4">
        <nav className="flex items-center gap-1.5 rounded-xl border border-slate-200/70 bg-white/65 p-1 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur">
          <NavItem href="/" label="AI图片" />
          <NavItem href="/video" label="AI视频" />
        </nav>
      </div>
    </header>
  );
}
