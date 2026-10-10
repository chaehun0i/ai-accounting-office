"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { DataImport } from "@/features/imports/data-import";
export default function Page() { return <CompanyPage href="/imports">{company => <DataImport company={company} />}</CompanyPage>; }
