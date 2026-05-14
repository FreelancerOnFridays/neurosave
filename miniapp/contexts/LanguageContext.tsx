"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { getT, type Lang, type TKey } from "@/lib/i18n";

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: TKey) => string;
}

const LanguageContext = createContext<LangCtx>({
  lang: "ru",
  setLang: () => {},
  t: getT("ru"),
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("ru");
  // Share the same SWR key as useSettings — no extra network request
  const { data: settings } = useSWR("/api/settings", api.settings.get);

  useEffect(() => {
    if (settings?.language) setLang(settings.language);
  }, [settings?.language]);

  return (
    <LanguageContext.Provider value={{ lang, setLang, t: getT(lang) }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLang() {
  return useContext(LanguageContext);
}
