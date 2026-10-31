import { THEMES, useTheme } from "@/components/providers/ThemeProvider"
import { Item, ItemActions, ItemContent, ItemGroup, ItemTitle } from "@/components/ui/Item"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select"

export function GeneralSection() {
  const { theme, setTheme } = useTheme()

  return <ItemGroup>
    <Item>
      <ItemContent>
        <ItemTitle>主题</ItemTitle>
      </ItemContent>
      <ItemActions>
        <Select value={theme} onValueChange={(value) => setTheme(value as typeof theme)}>
          <SelectTrigger id="theme" className="w-52" aria-label="主题">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {THEMES.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
          </SelectContent>
        </Select>
      </ItemActions>
    </Item>
  </ItemGroup>
}
