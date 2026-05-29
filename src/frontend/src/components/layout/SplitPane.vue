<template>
  <div class="split-pane">
    <div class="pane left-pane">
      <slot name="left" />
    </div>
    <div class="pane right-pane">
      <slot name="right" />
    </div>
  </div>
</template>

<style scoped>
.split-pane {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.pane {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.left-pane {
  width: 40%;
  min-width: 320px;
  border-right: 1px solid #e0e0e0;
}

.right-pane {
  flex: 1;
  position: relative;
}
</style>
