<script setup lang="ts">
import { computed } from "vue";
import { useDataDictionary } from "../../composables/useDataDictionary";
import { useSuggestions } from "../../composables/useSuggestions";
import type { TableInfo, Theme } from "../../types/dictionary";

const emit = defineEmits<{
	select: [question: string];
}>();

const { suggestions } = useSuggestions();
const { dictionary, fetchDictionary } = useDataDictionary();

fetchDictionary();

interface TableGroup {
	group: string;
	tables: TableInfo[];
}

function tablesByGroup(theme: Theme): TableGroup[] {
	const grouped = new Map<string, TableInfo[]>();
	for (const table of theme.tables) {
		const existing = grouped.get(table.group);
		if (existing) existing.push(table);
		else grouped.set(table.group, [table]);
	}
	return Array.from(grouped, ([group, tables]) => ({ group, tables }));
}

const themesWithGroups = computed(() => {
	if (!dictionary.value) return [];
	return dictionary.value.themes.map((theme) => ({
		theme,
		groups: tablesByGroup(theme),
	}));
});
</script>

<template>
  <div v-if="dictionary" class="suggestions">
    <div class="intro">
      <p class="intro-heading">Ruimtelijke data-assistent voor de Provincie Zuid-Holland</p>
      <p class="intro-text">
        Stel vragen over ruimtelijke data op H3-hexagonen.
        Beschikbare thema's zijn o.a. netcapaciteit, luchtkwaliteit, geluid, verkeer, OV-haltes en woningbouw.
      </p>
    </div>

    <details class="data-info">
      <summary class="data-info-toggle">Bekijk beschikbare data</summary>
      <div class="data-info-content">
        <details
          v-for="entry in themesWithGroups"
          :key="entry.theme.name"
          class="data-section"
        >
          <summary class="section-heading">{{ entry.theme.label }}</summary>
          <details
            v-for="group in entry.groups"
            :key="group.group"
            class="data-subsection"
          >
            <summary class="group-heading">{{ group.group }}</summary>
            <details
              v-for="table in group.tables"
              :key="table.name"
              class="data-subsubsection"
            >
              <summary class="table-heading">{{ table.name }}</summary>
              <ul class="col-list">
                <li v-for="col in table.columns" :key="col.name">
                  <strong>{{ col.name }}</strong>
                  <span v-if="col.description"> — {{ col.description }}</span>
                </li>
              </ul>
            </details>
          </details>
        </details>
      </div>
    </details>

    <template v-if="suggestions.length">
      <p class="suggestions-title">Stel een vraag, bijvoorbeeld:</p>
      <div v-for="group in suggestions" :key="group.theme" class="suggestion-group">
        <span class="theme-label">{{ group.theme }}</span>
        <div class="chips">
          <button
            v-for="q in group.questions"
            :key="q"
            class="chip"
            @click="emit('select', q)"
          >
            {{ q }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.suggestions {
  padding: 1rem;
}

.intro {
  margin-bottom: 1rem;
}

.intro-heading {
  font-size: 0.95rem;
  font-weight: 600;
  color: #1e3a5f;
  margin: 0 0 0.4rem;
}

.intro-text {
  font-size: 0.82rem;
  color: #4b5563;
  margin: 0 0 0.3rem;
  line-height: 1.4;
}

.intro-note {
  font-size: 0.75rem;
  color: #9ca3af;
  margin: 0;
  font-style: italic;
}

/* Data-info panel */
.data-info {
  margin-bottom: 1rem;
}

.data-info-toggle {
  font-size: 0.82rem;
  color: #2563eb;
  cursor: pointer;
  font-weight: 500;
}

.data-info-toggle:hover {
  text-decoration: underline;
}

.data-info-content {
  margin-top: 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 0.75rem;
  max-height: 20rem;
  overflow-y: auto;
}

.data-section {
  margin-bottom: 0.75rem;
}

.data-section:last-child {
  margin-bottom: 0;
}

.section-heading {
  font-size: 0.75rem;
  font-weight: 600;
  color: #1e3a5f;
  cursor: pointer;
  padding: 0.2rem 0;
}

.data-subsection {
  margin: 0.25rem 0 0.25rem 0.75rem;
}

.group-heading {
  font-size: 0.72rem;
  font-weight: 600;
  color: #2563eb;
  cursor: pointer;
  padding: 0.1rem 0;
}

.data-subsubsection {
  margin: 0.15rem 0 0.15rem 0.75rem;
}

.table-heading {
  font-size: 0.7rem;
  font-weight: 500;
  color: #4b5563;
  cursor: pointer;
  padding: 0.1rem 0;
  font-family: ui-monospace, SFMono-Regular, monospace;
}

.col-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 0.72rem;
  color: #4b5563;
  line-height: 1.5;
}

.col-list li {
  padding: 0.1rem 0;
}

.col-list strong {
  color: #1e3a5f;
  font-weight: 600;
}

.source-tag {
  display: inline-flex;
  margin-left: 0.4rem;
  padding: 0.05rem 0.35rem;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 0.68rem;
  font-weight: 600;
  vertical-align: middle;
}

.suggestions-title {
  font-size: 0.85rem;
  color: #6b7280;
  margin: 0 0 0.75rem;
}

.suggestion-group {
  margin-bottom: 0.75rem;
}

.theme-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.3rem;
}

.chip {
  padding: 0.3rem 0.7rem;
  background: #eff6ff;
  color: #2563eb;
  border: 1px solid #bfdbfe;
  border-radius: 16px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.chip:hover {
  background: #dbeafe;
  border-color: #93c5fd;
}
</style>
