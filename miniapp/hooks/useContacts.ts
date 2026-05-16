"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Contact, ContactSyncStatus } from "@/lib/types";

export function useContacts() {
  const { data: status, mutate: mutateStatus } = useSWR<ContactSyncStatus>(
    "/api/contacts/status",
    api.contacts.status,
    { refreshInterval: 10_000 }
  );

  const { data: contacts, mutate: mutateContacts } = useSWR<Contact[]>(
    "/api/contacts",
    api.contacts.list,
    { refreshInterval: 30_000 }
  );

  const { data: folders } = useSWR<{ name: string }[]>(
    status?.telethon_authorized ? "/api/contacts/folders" : null,
    api.contacts.folders
  );

  const [syncing, setSyncing] = useState(false);
  const [syncingFolder, setSyncingFolder] = useState<string | null>(null);

  const syncAll = async () => {
    setSyncing(true);
    try {
      await api.contacts.sync();
      await new Promise((r) => setTimeout(r, 3000));
      await Promise.all([mutateStatus(), mutateContacts()]);
    } finally {
      setSyncing(false);
    }
  };

  const syncFolder = async (folderName: string) => {
    setSyncingFolder(folderName);
    try {
      await api.contacts.syncFolder(folderName);
      await new Promise((r) => setTimeout(r, 2000));
      await Promise.all([mutateStatus(), mutateContacts()]);
    } finally {
      setSyncingFolder(null);
    }
  };

  return {
    status,
    contacts: contacts ?? [],
    folders: folders ?? [],
    syncing,
    syncingFolder,
    syncAll,
    syncFolder,
    mutateStatus,
  };
}
