import { defineConfig } from "@hey-api/openapi-ts"

export default defineConfig({
  input: "./openapi/processing.json",
  output: "./src/contracts/processing",

  plugins: [
    "legacy/axios",
    {
      name: "@hey-api/sdk",
      asClass: true,
      operationId: true,
      classNameBuilder: "{{name}}Service",
      methodNameBuilder: (operation) => {
        // @ts-expect-error
        let name: string = operation.name
        // @ts-expect-error
        const service: string = operation.service

        if (service && name.toLowerCase().startsWith(service.toLowerCase())) {
          name = name.slice(service.length)
        }

        return name.charAt(0).toLowerCase() + name.slice(1)
      },
    },
    {
      name: "@hey-api/schemas",
      type: "json",
    },
  ],
})
