import React from "react";
import Link from "next/link";

interface BrandMarkProps {
  size?: number;
  withWordmark?: boolean;
  href?: string;
  className?: string;
}

export function BrandMark({ size = 32, withWordmark = false, href, className = "" }: BrandMarkProps) {
  const mark = (
    <div
      className="relative flex items-center gap-2.5"
      style={{ height: size }}
    >
      <div
        className="relative grid place-items-center rounded-xl p-[2px] shadow-glow"
        style={{ width: size, height: size }}
      >
        <div
          className="absolute inset-0 rounded-xl"
          style={{
            background:
              "linear-gradient(135deg, #FF3B5C 0%, #E5264A 45%, #22D3EE 110%)",
          }}
        />
        <div className="relative w-full h-full rounded-[10px] bg-ink-950 grid place-items-center">
          <span
            className="font-mono font-black text-primary-400 leading-none"
            style={{ fontSize: size * 0.42 }}
          >
            S
          </span>
        </div>
        <span
          className="absolute -right-0.5 -top-0.5 block rounded-full bg-secondary-400 animate-pulse-ring"
          style={{ width: size * 0.16, height: size * 0.16 }}
        />
      </div>
      {withWordmark && (
        <div className="flex flex-col leading-none">
          <span className="font-extrabold tracking-[0.12em] text-white text-sm">
            SONIC<span className="text-primary-500">-REDA</span>
          </span>
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-muted-dim">
            Virtual Workstation
          </span>
        </div>
      )}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className={`group ${className}`}>
        <span className="block transition group-hover:scale-[1.03]">{mark}</span>
      </Link>
    );
  }
  return <div className={className}>{mark}</div>;
}
