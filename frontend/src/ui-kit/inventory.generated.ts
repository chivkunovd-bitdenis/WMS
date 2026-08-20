// СГЕНЕРИРОВАНО scripts/ui/ui_inventory.py — руками не править.
// Витрина показывает только то, что реально есть в коде экранов.
export type InventoryItem = {
  label: string
  tones: string[]
  variants: string[]
  files: string[]
  usages: number
}

export type ComponentInventoryItem = {
  name: string
  source: string
  zone: string
  purpose: string
  required_props: string[]
  optional_props: string[]
  observed_props: string[]
  files: string[]
  screen_ids: string[]
  usages: number
}

export type UiInventory = {
  chips: readonly InventoryItem[]
  statuses: readonly InventoryItem[]
  buttons: readonly InventoryItem[]
  alerts: readonly InventoryItem[]
  components: readonly ComponentInventoryItem[]
}

export const INVENTORY = {
  "chips": [
    {
      "label": "Заполнено",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfProductsCatalogScreen.tsx",
        "src/screens/v2/SellerProductsStockScreen.tsx"
      ],
      "usages": 2
    },
    {
      "label": "Нет ТЗ",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfProductsCatalogScreen.tsx",
        "src/screens/v2/SellerProductsStockScreen.tsx"
      ],
      "usages": 2
    },
    {
      "label": "—",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx",
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 2
    },
    {
      "label": "Вручную",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfProductsCatalogScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Готово",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsOrdersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Есть причины, которые нужно исправить",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FbsSupplyCreateDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Изменено ФФ",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/ff/FfSuppliesShipmentsPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Можно создать поставку",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FbsSupplyCreateDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Не требуется",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Нужен ЧЗ",
      "tones": [
        "primary"
      ],
      "variants": [],
      "files": [
        "src/screens/shared/HonestSignProductPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Отклонено WB",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsOrdersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "ПВЗ",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsOrdersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Поставка создана в WB",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsOrdersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Склад / СЦ",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsOrdersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Товары не выбраны — можно привязать позже",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/shared/MarkingImportDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "ЧЗ не требуется",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/ff/FfPackagingPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "есть",
      "tones": [
        "success"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyDrawer.tsx"
      ],
      "usages": 1
    },
    {
      "label": "нет",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyDrawer.tsx"
      ],
      "usages": 1
    }
  ],
  "statuses": [
    {
      "label": "Без проверки",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "В доставке",
      "tones": [
        "primary"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "В отгрузке",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Готовим к печати",
      "tones": [
        "info"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Дефект",
      "tones": [
        "error"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Завершён",
      "tones": [
        "success"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Нанесён",
      "tones": [
        "success"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Напечатан",
      "tones": [
        "primary"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Не напечатан",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Не проверена",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Новый",
      "tones": [
        "default",
        "info"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Отменён",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Отсортирован",
      "tones": [
        "primary"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Ошибка",
      "tones": [
        "error"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Проверен",
      "tones": [
        "success"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Проверена",
      "tones": [
        "success"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Проверяется",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Сборка",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Статус уточняется",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Требует исправления",
      "tones": [
        "error"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Упакован",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
      ],
      "usages": 1
    }
  ],
  "buttons": [
    {
      "label": "Отмена",
      "tones": [],
      "variants": [
        "text/primary"
      ],
      "files": [
        "src/components/BoxImportDialog.tsx",
        "src/components/MarkingPrintDialog.tsx",
        "src/components/ProductBarcodePrintDialog.tsx",
        "src/components/WbProductPickerDialog.tsx",
        "src/screens/ff/FfHonestSignReprintsPage.tsx",
        "src/screens/ff/FfManualProductCreateDialog.tsx",
        "src/screens/ff/FfPackagingPage.tsx",
        "src/screens/ff/FfProductTzImportDialog.tsx",
        "src/screens/ff/FfSellerCreateDialog.tsx",
        "src/screens/shared/MarkingImportDialog.tsx",
        "src/screens/shared/MarkingPoolProductsDialog.tsx",
        "src/screens/v2/FbsSupplyCreateDialog.tsx"
      ],
      "usages": 12
    },
    {
      "label": "Закрыть",
      "tones": [],
      "variants": [
        "contained/primary",
        "outlined/primary",
        "text/primary"
      ],
      "files": [
        "src/components/MarkingPrintDialog.tsx",
        "src/components/SellerMarketplaceUnloadDialog.tsx",
        "src/screens/ff/FfInboundRequestView.tsx",
        "src/screens/ff/FfPackagingPage.tsx",
        "src/screens/ff/FfSuppliesShipmentsPage.tsx",
        "src/screens/shared/MarkingProductCodesDialog.tsx",
        "src/screens/v2/FbsPrintPreviewDialog.tsx",
        "src/screens/v2/FfFbsPickList.tsx",
        "src/screens/v2/FfFbsSupplyDrawer.tsx"
      ],
      "usages": 9
    },
    {
      "label": "Печать",
      "tones": [],
      "variants": [
        "contained/primary",
        "outlined/primary"
      ],
      "files": [
        "src/components/ProductBarcodePrintDialog.tsx",
        "src/screens/v2/FfProductsCatalogScreen.tsx",
        "src/screens/v2/SellerProductsStockScreen.tsx"
      ],
      "usages": 3
    },
    {
      "label": "Обновить",
      "tones": [],
      "variants": [
        "text/primary"
      ],
      "files": [
        "src/screens/v2/MovementsScreen.tsx",
        "src/sections/OperationsSection.tsx"
      ],
      "usages": 2
    },
    {
      "label": "Повторить",
      "tones": [],
      "variants": [
        "text/inherit"
      ],
      "files": [
        "src/screens/ff/FfInboundSortingPanel.tsx",
        "src/screens/v2/FfFbsSupplyWorkspace.tsx"
      ],
      "usages": 2
    },
    {
      "label": "Вернуться к отгрузке",
      "tones": [],
      "variants": [
        "text/primary"
      ],
      "files": [
        "src/screens/ff/FfPackagingPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Вся лента пула",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/shared/HonestSignPoolPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Вся лента товара",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/shared/HonestSignProductPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Выйти",
      "tones": [],
      "variants": [
        "secondary/primary"
      ],
      "files": [
        "src/screens/ProfileLoadingScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Добавить",
      "tones": [],
      "variants": [
        "contained/primary"
      ],
      "files": [
        "src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Добавить всё",
      "tones": [],
      "variants": [
        "contained/warning"
      ],
      "files": [
        "src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Назад ко входу",
      "tones": [],
      "variants": [
        "text/primary"
      ],
      "files": [
        "src/screens/PublicAuthScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Осталось промаркировать",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/ff/FfPackagingPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Открыть «Селлеры»",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/components/DashboardCard.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Печать ТЗ",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/ff/FfSuppliesShipmentsPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Создать",
      "tones": [],
      "variants": [
        "contained/primary"
      ],
      "files": [
        "src/screens/ff/FfManualProductCreateDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Создать акт расхождений",
      "tones": [],
      "variants": [
        "outlined/secondary"
      ],
      "files": [
        "src/screens/v2/SellerDocumentsScreen.tsx"
      ],
      "usages": 1
    }
  ],
  "alerts": [
    {
      "label": "info: Дальше заявку обрабатывает фулфилмент.",
      "tones": [],
      "variants": [],
      "files": [
        "src/components/SellerMarketplaceUnloadDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Добавление селлеров доступно только администратору фулфилмента.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/SellersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Нет принятого товара для раскладки. Завершите приёмку в разделе «Приёмка».",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfInboundSortingPanel.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Нет товаров, ожидающих ручного подбора из ячеек.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyWorkspace.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Остаток КМ общий на весь пул, не на каждый товар.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/shared/HonestSignPoolPage.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Отгрузка проведена — состав короба только для просмотра.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Приёмка завершена — состав короба только для просмотра.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfInboundBoxAddDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Управление пользователями доступно только администратору фулфилмента.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfSettingsScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Управление складами и ячейками доступно только фулфилменту.",
      "tones": [],
      "variants": [],
      "files": [
        "src/sections/CatalogSection.tsx"
      ],
      "usages": 1
    },
    {
      "label": "success: Все товары подобраны. Перейдите к упаковке.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyWorkspace.tsx"
      ],
      "usages": 1
    },
    {
      "label": "success: Всё принятое разложено по ячейкам хранения.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfInboundSortingPanel.tsx"
      ],
      "usages": 1
    },
    {
      "label": "success: Подбор завершён. Этот этап доступен только для просмотра.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyWorkspace.tsx"
      ],
      "usages": 1
    },
    {
      "label": "success: Поставка уже передана в WB. Упаковка доступна только для просмотра.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyWorkspace.tsx"
      ],
      "usages": 1
    },
    {
      "label": "warning: Готовых изображений нет. Печать не будет открыта.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/FbsPrintPreviewDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "warning: Заявка не найдена или недоступна.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfInboundRequestView.tsx"
      ],
      "usages": 1
    },
    {
      "label": "warning: На складе нет ячеек хранения — создайте их в разделе «Ячейки».",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfInboundSortingPanel.tsx"
      ],
      "usages": 1
    },
    {
      "label": "warning: Нет доступного склада для создания заявки. Обратитесь к фулфилменту.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/SellerInboundDraftScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "warning: Нет напечатанных КМ для перепечатки",
      "tones": [],
      "variants": [],
      "files": [
        "src/components/MarkingPrintDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "warning: Состав изменён на складе после планирования селлером.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfSuppliesShipmentsPage.tsx"
      ],
      "usages": 1
    }
  ],
  "components": [
    {
      "name": "ActionGroup",
      "source": "frontend/src/ui-kit/Actions.tsx",
      "zone": "панель действий",
      "purpose": "Группа действий одной панели с ровной высотой и шириной кнопок.",
      "required_props": [],
      "optional_props": [
        "children"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ActionMenu",
      "source": "frontend/src/ui-kit/Menu.tsx",
      "zone": "панель действий",
      "purpose": "Меню вторичных действий строки или документа.",
      "required_props": [
        "title",
        "options"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "CheckboxField",
      "source": "frontend/src/ui-kit/Forms.tsx",
      "zone": "фильтры/форма",
      "purpose": "Канонический флажок формы.",
      "required_props": [
        "label",
        "checked",
        "onChange"
      ],
      "optional_props": [
        "disabled",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "DangerAction",
      "source": "frontend/src/ui-kit/Actions.tsx",
      "zone": "панель действий",
      "purpose": "Опасное действие: удаление, отмена, потеря данных.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "disabledReason"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "DataTable",
      "source": "frontend/src/ui-kit/DataTable.tsx",
      "zone": "таблица",
      "purpose": "Единственная каноническая таблица WMS.",
      "required_props": [
        "columns",
        "rows",
        "getRowKey"
      ],
      "optional_props": [
        "loading",
        "hasDiscrepancy",
        "empty",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "EmptyState",
      "source": "frontend/src/ui-kit/States.tsx",
      "zone": "состояния",
      "purpose": "Пустое состояние с действием или понятной подсказкой.",
      "required_props": [
        "title"
      ],
      "optional_props": [
        "hint",
        "action",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ErrorNotice",
      "source": "frontend/src/ui-kit/States.tsx",
      "zone": "состояния",
      "purpose": "Ошибка в теле экрана на языке склада.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "FilterBar",
      "source": "frontend/src/ui-kit/FilterBar.tsx",
      "zone": "фильтры",
      "purpose": "Панель поиска и фильтров над таблицей.",
      "required_props": [
        "search",
        "onSearchChange"
      ],
      "optional_props": [
        "searchPlaceholder",
        "children",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "IconAction",
      "source": "frontend/src/ui-kit/Actions.tsx",
      "zone": "панель действий",
      "purpose": "Иконка-действие с обязательной подсказкой.",
      "required_props": [
        "title",
        "children"
      ],
      "optional_props": [
        "testId",
        "onClick",
        "disabledReason"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "MarkChip",
      "source": "frontend/src/ui-kit/StatusChip.tsx",
      "zone": "статус/признак",
      "purpose": "Значок-признак товара, например ЧЗ.",
      "required_props": [
        "code",
        "hint"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ModalDialog",
      "source": "frontend/src/ui-kit/Dialog.tsx",
      "zone": "модалка",
      "purpose": "Канонический диалог подтверждения или формы.",
      "required_props": [
        "open",
        "title",
        "onClose"
      ],
      "optional_props": [
        "description",
        "children",
        "actions",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "PlanFactCell",
      "source": "frontend/src/ui-kit/Cells.tsx",
      "zone": "таблица",
      "purpose": "Ячейка план/факт с явным превышением.",
      "required_props": [
        "fact",
        "plan"
      ],
      "optional_props": [],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "PrimaryAction",
      "source": "frontend/src/ui-kit/Actions.tsx",
      "zone": "панель действий",
      "purpose": "Главное действие экрана или блока.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "disabledReason"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "PrintAction",
      "source": "frontend/src/ui-kit/Actions.tsx",
      "zone": "панель действий",
      "purpose": "Единый вид печати в строке или панели.",
      "required_props": [
        "what",
        "placement"
      ],
      "optional_props": [
        "onClick",
        "disabledReason",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ProductCell",
      "source": "frontend/src/ui-kit/Cells.tsx",
      "zone": "таблица",
      "purpose": "Ячейка товара: фото и SKU, без склеивания артикулов.",
      "required_props": [
        "sku"
      ],
      "optional_props": [
        "photo"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "QtyCell",
      "source": "frontend/src/ui-kit/Cells.tsx",
      "zone": "таблица",
      "purpose": "Числовая ячейка с табличными цифрами.",
      "required_props": [
        "value"
      ],
      "optional_props": [
        "muted"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ScannerLine",
      "source": "frontend/src/ui-kit/ScannerLine.tsx",
      "zone": "сканер",
      "purpose": "Строка состояния сканера.",
      "required_props": [
        "active",
        "expects"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ScreenHeader",
      "source": "frontend/src/ui-kit/States.tsx",
      "zone": "шапка",
      "purpose": "Название экрана и одна строка назначения.",
      "required_props": [
        "title"
      ],
      "optional_props": [
        "purpose"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ScreenSection",
      "source": "frontend/src/ui-kit/Layout.tsx",
      "zone": "каркас",
      "purpose": "Единый outlined-блок для рабочей зоны экрана.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ScreenShell",
      "source": "frontend/src/ui-kit/Layout.tsx",
      "zone": "каркас",
      "purpose": "Внешний каркас экрана с рабочей шириной WMS.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "SecondaryAction",
      "source": "frontend/src/ui-kit/Actions.tsx",
      "zone": "панель действий",
      "purpose": "Вторичное действие рядом с главным.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "disabledReason"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "SelectField",
      "source": "frontend/src/ui-kit/Forms.tsx",
      "zone": "фильтры/форма",
      "purpose": "Канонический выпадающий список.",
      "required_props": [
        "value",
        "options",
        "onChange"
      ],
      "optional_props": [
        "label",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "StatusChip",
      "source": "frontend/src/ui-kit/StatusChip.tsx",
      "zone": "статус/признак",
      "purpose": "Канонический статус документа или строки.",
      "required_props": [
        "label"
      ],
      "optional_props": [
        "tone",
        "hint",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "TableSkeletonBody",
      "source": "frontend/src/ui-kit/States.tsx",
      "zone": "таблица",
      "purpose": "Скелетон загрузки строк таблицы.",
      "required_props": [
        "columns"
      ],
      "optional_props": [
        "rows"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "TabsBar",
      "source": "frontend/src/ui-kit/Forms.tsx",
      "zone": "навигация/вкладки",
      "purpose": "Канонические вкладки внутри рабочего экрана.",
      "required_props": [
        "value",
        "tabs",
        "onChange"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "TextCell",
      "source": "frontend/src/ui-kit/Cells.tsx",
      "zone": "таблица",
      "purpose": "Текстовая ячейка с подсказкой полного значения.",
      "required_props": [
        "value"
      ],
      "optional_props": [
        "width"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "TextInput",
      "source": "frontend/src/ui-kit/Forms.tsx",
      "zone": "фильтры/форма",
      "purpose": "Каноническое поле ввода.",
      "required_props": [],
      "optional_props": [
        "label",
        "value",
        "onChange",
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    },
    {
      "name": "ToolbarLine",
      "source": "frontend/src/ui-kit/Layout.tsx",
      "zone": "панель действий",
      "purpose": "Строка действий или вкладок над рабочей зоной.",
      "required_props": [
        "children"
      ],
      "optional_props": [
        "testId"
      ],
      "observed_props": [],
      "files": [],
      "screen_ids": [],
      "usages": 0
    }
  ]
} as const satisfies UiInventory
