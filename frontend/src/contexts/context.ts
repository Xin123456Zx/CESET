import { defineComponent, provide, inject, shallowReactive, type PropType } from 'vue';

export function createContext<T extends object>(defaultValue: T) {
  const KEY = Symbol('CREATE_CONTEXT_KEY');

  const Provider = defineComponent({
    props: {
      value: {
        type: Object as PropType<T>,
        required: true,
      },
    },
    setup(props, ctx) {
      // ✅ Ensure `reactive` data is passed through correctly

      // @ts-ignore
      const state = shallowReactive(props.value);
      provide(KEY, state);
      return () => ctx.slots.default?.();
    },
  });

  const useContext = () => {
    // ✅ Avoid `undefined` errors by falling back to `defaultValue`
    return inject<T>(KEY, shallowReactive(defaultValue));
  };

  return {
    Provider,
    useContext,
  };
}
