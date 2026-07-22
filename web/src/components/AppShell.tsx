"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Overview" },
  { href: "/exams", label: "Exams" },
  { href: "/documents", label: "Documents" },
  { href: "/search", label: "Search" },
  { href: "/questions", label: "Questions" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="relative min-h-full">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-24 top-0 h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,rgba(45,212,191,0.18),transparent_65%)] blur-2xl" />
        <div className="absolute -right-20 top-40 h-[24rem] w-[24rem] rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.14),transparent_65%)] blur-2xl" />
        <div
          className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
      </div>

      <header className="relative z-10 border-b border-white/8 bg-[#07151c]/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-4 py-4 sm:px-6">
          <Link href="/" className="group flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-teal-400/15 ring-1 ring-teal-300/30 transition group-hover:bg-teal-400/25">
              <span className="font-display text-lg font-semibold text-teal-300">Q</span>
            </span>
            <div>
              <p className="font-display text-lg leading-none tracking-tight text-stone-50">
                QuestionBank
              </p>
              <p className="mt-1 text-xs text-stone-400">Knowledge base studio</p>
            </div>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {nav.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-lg px-3 py-2 text-sm transition",
                    active
                      ? "bg-white/10 text-white"
                      : "text-stone-400 hover:bg-white/5 hover:text-stone-100",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <nav className="flex gap-1 overflow-x-auto border-t border-white/5 px-4 py-2 md:hidden">
          {nav.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "shrink-0 rounded-lg px-3 py-1.5 text-sm",
                  active
                    ? "bg-white/10 text-white"
                    : "text-stone-400 hover:text-stone-100",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>
    </div>
  );
}
