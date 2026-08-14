import {createContext} from './context.ts'


const { Provider: ParamasContextProvider,useContext:paramsUsecontext } = createContext<any>({});

export {ParamasContextProvider,paramsUsecontext}