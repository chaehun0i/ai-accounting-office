"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { OnboardingWorkspace } from "@/features/onboarding/onboarding-workspace";
export default function Page() { return <CompanyPage href="/onboarding">{company => <OnboardingWorkspace company={company} />}</CompanyPage>; }
