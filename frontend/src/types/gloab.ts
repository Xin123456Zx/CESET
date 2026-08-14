export { }
declare global {
  type LocaleType = "zh-CN" | "en"
  const isApp: string;

  type ProblemResolveType = "DEFAULT" | "UP" | "DOWN"
  interface BaseResponse<T> {
    success: boolean
    data?: T
    rows?: T
    code: number
    message?: string,
    [key: string]: any
  }
  // Make the specified fields optional
  type Options<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>
  // Combine an object's keys into a union type
  type GetKey<T> = {
    [K in keyof T]: K
  }[keyof T]
  type GtagType = "select_game" | "chat" | "like" | "unlike" | "share" | "conversion" | "view_source"
  type PLANTFORM =
    | "APP-PLUS"
    | "APP-PLUS-NVUE"
    | "H5"
    | "MP-WEIXIN"
    | "MP-ALIPAY"
    | "MP-BAIDU"
    | "MP-TOUTIAO"
    | "MP-QQ"
    | "MP-360"
  interface Window {
    gtag: (event: string, type: GtagType, option: any) => void
    location: Location
  }
  export interface Language {
    name: string
  }
  
  export interface LocaleDropdownType {
    lang: LocaleType
    name?: string
    elLocale?: Language
  }
  export type TabType = "Green" | "Blue" 

 export interface CountryFlagType {
    title: string
    select: boolean
    icon: string
   "nameEn": string 
   "listName": string
    id:number|string
    slot:object
    content:string
  }

}
