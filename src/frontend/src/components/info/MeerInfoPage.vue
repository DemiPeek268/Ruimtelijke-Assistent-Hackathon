<script setup lang="ts">
</script>

<template>
  <div class="meer-info-page">
    <div class="meer-info-inner">
      <div class="meer-info-header">
        <h2>Over de Ruimtelijke Assistent</h2>
      </div>

      <div class="meer-info-body">
        <!-- Aanleiding -->
        <section class="info-section">
          <h3>Aanleiding</h3>
          <p>
            Binnen onze organisatie werken we met ruimtelijke datasets die informatie bevatten over gebieden in Nederland, opgedeeld in hexagonale gebiedseenheden (H3-hexagonen).
            Deze datasets bevatten honderden kolommen met uiteenlopende gegevens: van bevolkingsaantallen en woningkenmerken tot milieudata en nabijheid van voorzieningen.

            Het probleem is dat deze data momenteel alleen toegankelijk is voor technische gebruikers die SQL of Python beheersen. Niet-technische collega's, beleidsmedewerkers en bestuurders kunnen de data niet zelfstandig bevragen, waardoor ze afhankelijk zijn van analisten voor elk inzicht.
          </p>
        </section>

        <!-- Doel -->
        <section class="info-section">
          <h3>Doel</h3>
          <p>
            De Ruimtelijke Assistent stelt <strong>elke gebruiker</strong> — ongeacht technische
            kennis — in staat om in gewoon Nederlands vragen te stellen over ruimtelijke data. Stel
            een vraag, en de assistent zoekt de juiste gegevens op, legt zijn redenering uit, en
            toont het resultaat op een interactieve kaart.
          </p>
        </section>

        <!-- Wat kun je ermee doen? -->
        <section class="info-section">
          <h3>Wat kun je ermee doen?</h3>

          <div class="feature-list">
            <div class="feature-item">
              <span class="feature-icon">💬</span>
              <div>
                <strong>Stel vragen in gewoon Nederlands</strong>
                <p>Geen SQL nodig. Typ je vraag zoals je die aan een collega zou stellen, en de
                assistent vertaalt hem naar een query en toont de resultaten op de kaart.</p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-icon">🔄</span>
              <div>
                <strong>Verduidelijkende dialoog</strong>
                <p>
                  Als je vraag meerdere interpretaties heeft, een plaatsnaam niet precies overeenkomt,
                  of de assistent niet zeker weet welke kolom je bedoelt, stelt hij een genummerde
                  vervolgvraag. Je kiest een optie of herformuleert, en de assistent gaat verder.
                  Dit is geen foutmelding — het is hoe je samen met de assistent precies de data
                  vindt die je zoekt.
                </p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-icon">📍</span>
              <div>
                <strong>Ruimtelijke vragen op locatie</strong>
                <p>Vraag naar gebieden binnen een bepaalde afstand van een gebied, plek, voorziening of
                adres. Bijvoorbeeld: "Welke wijken liggen binnen 5 km van station Delft?" De
                assistent zoekt de coördinaten op en berekent de juiste gebieden.</p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-icon">🔍</span>
              <div>
                <strong>Vervolgvragen stellen</strong>
                <p>De assistent onthoudt de context van het gesprek. Stel vervolgvragen op eerdere
                antwoorden zonder alles opnieuw te hoeven uitleggen.</p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-icon">🔎</span>
              <div>
                <strong>Inzicht in elk antwoord</strong>
                <p>
                  Terwijl de assistent nadenkt kan je de verschillende stappen volgen in de chat. Voor meer inzicht in de redenering kan je middels de toggle ook het denkproces per stap inzien.
                </p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-icon">💡</span>
              <div>
                <strong>Slimme suggesties</strong>
                <p>Weet je niet waar je moet beginnen? De assistent toont voorbeeldvragen die
                aansluiten bij de beschikbare data.</p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-icon">🎨</span>
              <div>
                <strong>Kaartvisualisaties</strong>
                <p>
                  Resultaten worden weergegeven als gekleurde hexagonen — hoe donkerder de kleur,
                  hoe hoger of lager de waarde ten opzichte van de rest. Bij numerieke kolommen
                  kies je tussen twee modi: lineair (volledige waardebreedte
                  evenredig verdeeld) of percentielen (schaal afgestemd op P2–P98,
                  zodat extreme uitschieters het beeld niet verstoren). Categorische kolommen
                  krijgen automatisch een eigen kleur per unieke waarde.
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Hoe werkt het? -->
        <section class="info-section">
          <h3>Hoe werkt het?</h3>
          <p>In vier stappen van vraag tot kaart:</p>

          <div class="workflow-steps">
            <div class="workflow-step">
              <div class="step-number">1</div>
              <div class="step-content">
                <strong>Jouw vraag</strong>
                <span>Je typt een vraag in het chatpaneel</span>
              </div>
            </div>
            <div class="workflow-arrow">→</div>
            <div class="workflow-step">
              <div class="step-number">2</div>
              <div class="step-content">
                <strong>Assistent begrijpt</strong>
                <span>Intentie analyseren, evt. verduidelijking vragen</span>
              </div>
            </div>
            <div class="workflow-arrow">→</div>
            <div class="workflow-step">
              <div class="step-number">3</div>
              <div class="step-content">
                <strong>Zoekt de data op</strong>
                <span>Genereert en voert een SQL-query uit</span>
              </div>
            </div>
            <div class="workflow-arrow">→</div>
            <div class="workflow-step">
              <div class="step-number">4</div>
              <div class="step-content">
                <strong>Kaart + uitleg</strong>
                <span>Resultaten verschijnen op de kaart met een tekstuele toelichting</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Veiligheid & transparantie -->
        <section class="info-section">
          <h3>Veiligheid &amp; transparantie</h3>
          <p>
            Alle queries zijn <strong>read-only</strong> — de assistent kan geen data aanpassen of
            verwijderen. Wat de assistent doet is altijd inzichtelijk via het Inzicht-paneel: de
            SQL, de redenering, de prompts en de timings zijn zichtbaar voor elke vraag.
          </p>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.meer-info-page {
  flex: 1;
  overflow-y: auto;
  background: #1a1a2e;
  color: #e0e0e0;
}

.meer-info-inner {
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.meer-info-header {
  margin-bottom: 1.5rem;
}

.meer-info-header h2 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
  color: #fff;
}

.info-section {
  margin-bottom: 2rem;
}

.info-section:last-child {
  margin-bottom: 0;
}

.info-section h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #3b82f6;
  margin: 0 0 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #2a2a4a;
}

.info-section > p {
  margin: 0 0 0.75rem;
  line-height: 1.6;
  font-size: 0.9rem;
  color: #ccc;
}

/* Feature list */
.feature-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.feature-item {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
}

.feature-icon {
  font-size: 1.2rem;
  flex-shrink: 0;
  margin-top: 0.05rem;
}

.feature-item strong {
  display: block;
  font-size: 0.875rem;
  color: #fff;
  margin-bottom: 0.2rem;
}

.feature-item p {
  margin: 0;
  font-size: 0.825rem;
  line-height: 1.55;
  color: #aaa;
}

/* Workflow steps */
.workflow-steps {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.75rem;
}

.workflow-step {
  flex: 1;
  min-width: 130px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  background: rgba(59, 130, 246, 0.07);
  border: 1px solid #2a2a4a;
  border-radius: 8px;
  padding: 0.85rem 0.75rem;
  text-align: center;
}

.step-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #3b82f6;
  color: #fff;
  font-size: 0.8rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-content {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.step-content strong {
  font-size: 0.8rem;
  color: #fff;
}

.step-content span {
  font-size: 0.72rem;
  color: #888;
  line-height: 1.4;
}

.workflow-arrow {
  display: flex;
  align-items: center;
  color: #3b82f6;
  font-size: 1.2rem;
  flex-shrink: 0;
}
</style>
