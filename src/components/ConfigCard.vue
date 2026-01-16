<template>
  <q-dialog persistent ref="dialogRef" @hide="onDialogHide" v-bind="$attrs">
    <q-card class="q-pa-md q-ma-md" bordered>
        <q-card-section align="right">
          <q-btn v-if="false" color="primary" label="cancel" type="submit" @click="onDialogCancel" />
          <q-btn unelevated color="primary" label="關閉" @click="onDialogOK" />
        </q-card-section>

        <q-card-section style="max-height: 75vh" class="scroll">
          <span>
            <q-btn flat @click="toggleDark()" :label="isDarkActive() ? '🌕' : '🖤'" />
            <q-btn flat label="A-" :disable="fontsize === 7" @click="update({fontsize: `${Math.min(7,fontsize+1)}`})" />
            <q-btn flat label="A+" :disable="fontsize === 1" @click="update({fontsize: `${Math.max(1,fontsize-1)}`})" />
          </span>
        </q-card-section>

        <q-card-actions>
        </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent } from 'quasar';
import { useAppConfig } from 'src/services/useAppConfig';
import { isDarkActive, toggleDark } from 'src/services/utils';
import { computed } from 'vue';
defineEmits([...useDialogPluginComponent.emits]);
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent();
const { config, update } = useAppConfig()
const fontsize = computed(() => Number(config.value.fontsize || 7))
</script>