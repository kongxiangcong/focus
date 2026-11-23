import { accents, type Accent, type Theme } from "./appearance";

const themes = [["system", "跟随系统"], ["light", "浅色"], ["dark", "深色"]] as const;
const accentLabels: Record<Accent, string> = { blue: "钴蓝白", green: "松青绿白", red: "绯红白", neutral: "极简黑白" };

export function AppearanceThemePicker({ theme, accent, onTheme, onAccent }: {
  theme: Theme; accent: Accent; onTheme: (theme: Theme) => void; onAccent: (accent: Accent) => void;
}) {
  return <>
    <fieldset className="settings-theme-choices">
      <legend>主题</legend>
      <div className="settings-theme-options">
        {themes.map(([value, label]) => <label key={value}>
          <input type="radio" name="focus-theme" checked={theme === value} onChange={() => onTheme(value)} />
          <span>{label}</span>
        </label>)}
      </div>
    </fieldset>
    {theme === "dark" ? <p className="settings-theme-note">浅色配色已保留，切回浅色生效</p> :
      <fieldset className="settings-theme-choices">
        <legend>浅色配色</legend>
        <div className="settings-theme-options">
          {accents.map(value => <label key={value}>
            <input type="radio" name="focus-accent" checked={accent === value} onChange={() => onAccent(value)} />
            <span><i aria-hidden="true" data-swatch={value} />{accentLabels[value]}</span>
          </label>)}
        </div>
      </fieldset>}
  </>;
}
