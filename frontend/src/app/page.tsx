"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { Logo } from "@/components/brand/logo";
import { SkeletonFighter } from "@/components/landing/skeleton-fighter";
import { ButtonLink } from "@/components/ui/button";
import {
  ArrowRightIcon,
  BoltIcon,
  EyeIcon,
  ShieldIcon,
  TargetIcon,
  UploadIcon,
} from "@/components/ui/icons";
import { STRIKE_META } from "@/lib/strike-meta";

const TICKER = [
  "Jab",
  "Cross",
  "Hook",
  "Uppercut",
  "Body shot",
  "Guard score",
  "Telegraph check",
  "Hand speed",
  "Strikes per minute",
  "Corner advice",
  "Drills",
];

const STEPS = [
  {
    n: "01",
    title: "Film a round",
    body: "Bag work, pads, shadow boxing, or sparring. Phone on a tripod, whole body in frame. Upload the clip or pull one from YouTube.",
  },
  {
    n: "02",
    title: "We track every joint",
    body: "A pose model follows 17 points on your body through every frame, then picks out each punch from how your wrists move.",
  },
  {
    n: "03",
    title: "Get your corner talk",
    body: "A punch-by-punch timeline over your own footage, the habits that leave you open, one thing to fix first, and drills to fix it.",
  },
];

const FEATURES = [
  {
    icon: TargetIcon,
    title: "Every punch, logged",
    body: "Jabs, crosses, hooks, uppercuts, and body shots, each with the hand that threw it, how fast it moved, and the exact moment in the clip.",
  },
  {
    icon: ShieldIcon,
    title: "Guard check on every strike",
    body: "When you punch, where is your other hand? CornerMan measures it against your chin each time and scores how often you stay covered.",
  },
  {
    icon: EyeIcon,
    title: "Telegraph detection",
    body: "An elbow that flares before the punch leaves tells your opponent what is coming. Those punches get flagged so you can see the tell yourself.",
  },
  {
    icon: BoltIcon,
    title: "Advice you can drill",
    body: "Coaching written from your numbers in a corner-man voice, plus drills matched to the mistakes that showed up in this round.",
  },
];

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [user, loading, router]);

  return (
    <div className="overflow-x-clip">
      {/* Top bar */}
      <header className="mx-auto flex h-18 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo />
        <nav className="flex items-center gap-2 sm:gap-4">
          <Link
            href="/login"
            className="px-2 font-display text-[0.9375rem] font-bold uppercase tracking-wider text-mute hover:text-chalk"
          >
            Sign in
          </Link>
          <ButtonLink href="/register" size="sm">
            Start free
          </ButtonLink>
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:px-8 lg:pb-24 lg:pt-16">
        <div className="animate-rise">
          <p className="eyebrow mb-5 flex items-center gap-3 text-blood">
            <span className="h-px w-10 bg-blood" />
            AI striking analysis
          </p>
          <h1 className="display text-[clamp(3.5rem,10vw,7.5rem)] text-chalk">
            Your corner
            <br />
            <span className="text-blood">never blinks.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-mute">
            Upload a round of bag work, pads, or sparring. CornerMan tracks every punch you
            throw, catches the moments your guard drops, and tells you what to fix first.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <ButtonLink href="/register" size="lg">
              <UploadIcon /> Break down my film
            </ButtonLink>
            <ButtonLink href="/login" size="lg" variant="outline">
              I have an account
            </ButtonLink>
          </div>
          <p className="mt-5 font-mono text-xs uppercase tracking-widest text-dim">
            Free · 5 analyses a day · MP4 or MOV
          </p>
        </div>

        {/* Live skeleton */}
        <div className="animate-rise [animation-delay:150ms]">
          <div className="hud-frame mx-auto max-w-md border border-line bg-panel/70">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <span className="eyebrow flex items-center gap-2 text-chalk">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inset-0 animate-ping-slow rounded-full bg-blood" />
                  <span className="relative h-2 w-2 rounded-full bg-blood" />
                </span>
                Tracking
              </span>
              <span className="eyebrow">17 keypoints</span>
            </div>
            <SkeletonFighter className="w-full" />
            <div className="grid grid-cols-3 border-t border-line text-center">
              {[
                ["Orthodox", "Stance"],
                ["Jab · Cross", "Combo"],
                ["1 flag", "Guard"],
              ].map(([value, label]) => (
                <div key={label} className="border-r border-line px-2 py-3 last:border-r-0">
                  <p className="font-display text-lg font-bold uppercase italic text-chalk">
                    {value}
                  </p>
                  <p className="eyebrow mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          </div>
          <p className="mt-3 text-center text-xs text-dim">
            Illustration of the tracking overlay. Watch the guard line when the cross goes out.
          </p>
        </div>
      </section>

      {/* Ticker */}
      <div className="border-y border-line bg-panel/60 py-3" aria-hidden="true">
        <div className="flex w-max animate-marquee gap-10 pr-10">
          {[...TICKER, ...TICKER].map((item, i) => (
            <span
              key={i}
              className="flex items-center gap-10 font-display text-xl font-bold uppercase italic tracking-wide text-mute"
            >
              {item}
              <span className="octagon h-2.5 w-2.5 bg-blood" />
            </span>
          ))}
        </div>
      </div>

      {/* How it works */}
      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <p className="eyebrow mb-2 text-blood">How it works</p>
        <h2 className="display max-w-3xl text-5xl text-chalk sm:text-6xl">
          Three rounds from clip to game plan
        </h2>
        <div className="mt-12 grid gap-px overflow-hidden rounded-md border border-line bg-line md:grid-cols-3">
          {STEPS.map((step) => (
            <div key={step.n} className="bg-panel p-7">
              <p className="display text-6xl text-transparent [-webkit-text-stroke:1.5px_var(--color-blood)]">
                {step.n}
              </p>
              <h3 className="display mt-5 text-3xl text-chalk">{step.title}</h3>
              <p className="mt-3 leading-relaxed text-mute">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* What it catches */}
      <section className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="eyebrow mb-2 text-blood">What it catches</p>
            <h2 className="display text-5xl text-chalk sm:text-6xl">
              The stuff you can&apos;t see while you&apos;re throwing
            </h2>
            <p className="mt-5 leading-relaxed text-mute">
              Every strike lands on a timeline you can click to jump straight to that moment
              in your video. Disagree with a call? Dispute it with one tap.
            </p>
            <div className="mt-7 flex flex-wrap gap-2">
              {(["jab", "cross", "hook", "uppercut", "body_shot"] as const).map((type) => (
                <span
                  key={type}
                  className="chamfer px-3.5 py-1.5 font-display text-sm font-bold uppercase tracking-wider text-canvas"
                  style={{ backgroundColor: STRIKE_META[type].color }}
                >
                  {STRIKE_META[type].label}
                </span>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {FEATURES.map(({ icon: FeatureIcon, title, body }) => (
              <div
                key={title}
                className="group rounded-md border border-line bg-panel/80 p-6 transition-colors hover:border-blood/60"
              >
                <FeatureIcon className="text-3xl text-blood" />
                <h3 className="display mt-4 text-2xl text-chalk">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mute">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Straight talk */}
      <section className="border-y border-line bg-panel/60">
        <div className="mx-auto grid max-w-7xl grid-cols-1 gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[auto_1fr] lg:items-center lg:px-8">
          <div className="tape h-2 w-32 lg:h-32 lg:w-2" />
          <div>
            <h2 className="display text-4xl text-chalk sm:text-5xl">
              Built by a fighter. Honest about its limits.
            </h2>
            <p className="mt-4 max-w-3xl leading-relaxed text-mute">
              CornerMan was built by someone who has fought and coached. It reads pose, not
              intent: it follows one fighter per clip, works best with a steady side-on or
              three-quarter angle, and it will miss things a good coach would catch. Use it
              between sessions with your coach, not instead of them.
            </p>
          </div>
        </div>
      </section>

      {/* Final call */}
      <section className="mx-auto max-w-7xl px-4 py-24 text-center sm:px-6 lg:px-8">
        <h2 className="display text-6xl text-chalk sm:text-8xl">
          Got a round on <span className="text-blood">your phone?</span>
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-lg text-mute">
          Upload it and see your striking broken down punch by punch.
        </p>
        <ButtonLink href="/register" size="lg" className="mt-9">
          Get my breakdown <ArrowRightIcon />
        </ButtonLink>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-6 sm:px-6 lg:px-8">
          <Logo />
          <p className="font-mono text-xs uppercase tracking-widest text-dim">
            Train smart. Protect yourself at all times.
          </p>
        </div>
      </footer>
    </div>
  );
}
