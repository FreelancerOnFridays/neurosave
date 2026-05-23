"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { Contact, ContactSyncStatus } from "@/lib/types";

export function useContacts() {
  const { data: status, mutate: mutateStatus } = useSWR<ContactSyncStatus>(
    "/api/contacts/status",
    api.contacts.status,
    { refreshInterval: 30_000 }
  );

  const { data: contacts, mutate: mutateContacts } = useSWR<Contact[]>(
    "/api/contacts",
    api.contacts.list,
    { refreshInterval: 30_000 }
  );

  return {
    status,
    contacts: contacts ?? [],
    mutateStatus,
    mutateContacts,
  };
}
