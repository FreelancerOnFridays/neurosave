"use client";

const TIMEZONES: { value: string; label: string }[] = [
  { value: "UTC", label: "UTC (±0)" },
  { value: "Europe/London", label: "Лондон / London (UTC+0/+1)" },
  { value: "Europe/Berlin", label: "Берлин / Berlin (UTC+1/+2)" },
  { value: "Europe/Warsaw", label: "Варшава / Warsaw (UTC+1/+2)" },
  { value: "Europe/Paris", label: "Париж / Paris (UTC+1/+2)" },
  { value: "Europe/Kiev", label: "Киев / Kyiv (UTC+2/+3)" },
  { value: "Europe/Helsinki", label: "Хельсинки / Helsinki (UTC+2/+3)" },
  { value: "Europe/Moscow", label: "Москва / Moscow (UTC+3)" },
  { value: "Europe/Istanbul", label: "Стамбул / Istanbul (UTC+3)" },
  { value: "Asia/Dubai", label: "Дубай / Dubai (UTC+4)" },
  { value: "Asia/Yekaterinburg", label: "Екатеринбург (UTC+5)" },
  { value: "Asia/Almaty", label: "Алматы / Almaty (UTC+6)" },
  { value: "Asia/Novosibirsk", label: "Новосибирск (UTC+7)" },
  { value: "Asia/Krasnoyarsk", label: "Красноярск (UTC+7)" },
  { value: "Asia/Irkutsk", label: "Иркутск (UTC+8)" },
  { value: "Asia/Shanghai", label: "Шанхай / Shanghai (UTC+8)" },
  { value: "Asia/Singapore", label: "Сингапур / Singapore (UTC+8)" },
  { value: "Asia/Tokyo", label: "Токио / Tokyo (UTC+9)" },
  { value: "Asia/Yakutsk", label: "Якутск (UTC+9)" },
  { value: "Asia/Vladivostok", label: "Владивосток (UTC+10)" },
  { value: "Australia/Sydney", label: "Сидней / Sydney (UTC+10/+11)" },
  { value: "Pacific/Auckland", label: "Окленд / Auckland (UTC+12/+13)" },
  { value: "America/Los_Angeles", label: "Лос-Анджелес (UTC-8/-7)" },
  { value: "America/Denver", label: "Денвер / Denver (UTC-7/-6)" },
  { value: "America/Chicago", label: "Чикаго / Chicago (UTC-6/-5)" },
  { value: "America/New_York", label: "Нью-Йорк / New York (UTC-5/-4)" },
  { value: "America/Sao_Paulo", label: "Сан-Паулу / São Paulo (UTC-3/-2)" },
];

interface TimezoneSelectProps {
  value: string;
  onChange: (tz: string) => void;
}

export function TimezoneSelect({ value, onChange }: TimezoneSelectProps) {
  const knownOption = TIMEZONES.find((t) => t.value === value);

  return (
    <select
      value={knownOption ? value : "__custom__"}
      onChange={(e) => {
        if (e.target.value !== "__custom__") onChange(e.target.value);
      }}
      className="text-sm bg-tg-secondary text-tg-text rounded-xl px-3 py-1.5 outline-none border border-tg-hint/20 focus:border-tg-accent/50 max-w-[200px]"
    >
      {!knownOption && (
        <option value="__custom__">{value}</option>
      )}
      {TIMEZONES.map((tz) => (
        <option key={tz.value} value={tz.value}>
          {tz.label}
        </option>
      ))}
    </select>
  );
}
