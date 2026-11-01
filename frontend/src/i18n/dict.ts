const ru: Record<string, string> = {
  appName: 'PredictorLab',
  navModels: 'MODELS',
  navNew: 'NEW MODEL',
  navAdmin: 'ADMIN',
  logout: 'Выйти',
  login: 'Войти',
  email: 'Email',
  password: 'Пароль',
  loading: 'Загрузка…',
  accessDenied: 'Недостаточно прав',
  needAuth: 'Требуется вход',
}

const en: Record<string, string> = {
  logout: 'Sign out',
}

export const dict = { ru, en }
export type Lang = keyof typeof dict
