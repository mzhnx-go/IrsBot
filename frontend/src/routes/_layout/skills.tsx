import { createFileRoute } from "@tanstack/react-router"

import SkillsSettings from "@/components/Skills/SkillsSettings"

export const Route = createFileRoute("/_layout/skills")({
  component: SkillsPage,
  head: () => ({
    meta: [
      {
        title: "技能 - IrsBot",
      },
    ],
  }),
})

function SkillsPage() {
  return <SkillsSettings />
}
