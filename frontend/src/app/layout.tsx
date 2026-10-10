import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { OfficeProviders } from "@/features/navigation/office-shell";

export const metadata: Metadata = {
  title: "AI Accounting Office",
  description: "회계와 세무 업무를 한곳에서 관리하는 서비스",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="ko"><body><OfficeProviders>{children}</OfficeProviders></body></html>;
}
