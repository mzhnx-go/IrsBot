import { createFileRoute } from "@tanstack/react-router"

import PersonaSettings from "@/components/Personas/PersonaSettings"

export const Route = createFileRoute("/_layout/personas")({
  component: PersonasPage,
  head: () => ({
    meta: [
      {
        title: "人设 - IrsBot",
      },
    ],
  }),
})

function PersonasPage() {
  return <PersonaSettings />
}
