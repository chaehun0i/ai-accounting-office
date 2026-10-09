import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "AI Accounting Office",
  description: "회계·세무 업무를 위한 개발 기반",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}
