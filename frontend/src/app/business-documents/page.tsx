"use client";
import { DocumentWorkspace } from "@/features/business-documents/document-workspace";
import { CompanyPage } from "@/features/navigation/office-shell";
export default function Page() { return <CompanyPage href="/business-documents">{company => <DocumentWorkspace key={company.id} company={company} />}</CompanyPage>; }
