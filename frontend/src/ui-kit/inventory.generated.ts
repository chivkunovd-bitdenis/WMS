// СГЕНЕРИРОВАНО scripts/ui/ui_inventory.py — руками не править.
// Витрина показывает только то, что реально есть в коде экранов.
export type InventoryItem = {
  label: string
  tones: string[]
  variants: string[]
  files: string[]
  usages: number
}

export const INVENTORY = {
  "chips": [
    {
      "label": "ЧЗ",
      "tones": [
        "info"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfProductsCatalogScreen.tsx",
        "src/screens/v2/SellerProductsStockScreen.tsx"
      ],
      "usages": 2
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
      "label": "Сводка не запускалась",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/MovementsScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Сдаём без Честного знака",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsSupplyWorkspace.tsx"
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
      "label": "Этикетка напечатана",
      "tones": [
        "success"
      ],
      "variants": [],
      "files": [
        "src/screens/ff/FfInboundRequestView.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Ячейка не выбрана",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/ff/FfMpUnloadPickPanel.tsx"
      ],
      "usages": 1
    },
    {
      "label": "не запускалась",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "не требуется",
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
      "label": "требует проверки",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "—",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/components/fbs/FbsChips.tsx"
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
      "label": "Отклонено WB",
      "tones": [
        "error"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsOrdersScreen.tsx"
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
    },
    {
      "label": "нечего публиковать",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "ошибка публикации",
      "tones": [
        "error"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "публикация включена",
      "tones": [
        "default",
        "success",
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "публикация выключена",
      "tones": [
        "default"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "склад не сопоставлен",
      "tones": [
        "warning"
      ],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
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
        "src/components/BoxLabelPrintDialog.tsx",
        "src/components/MarkingPrintDialog.tsx",
        "src/components/ProductBarcodePrintDialog.tsx",
        "src/components/WbProductPickerDialog.tsx",
        "src/screens/ff/FfHonestSignReprintsPage.tsx",
        "src/screens/ff/FfInboundQueuePage.tsx",
        "src/screens/ff/FfManualProductCreateDialog.tsx",
        "src/screens/ff/FfPackagingPage.tsx",
        "src/screens/ff/FfProductTzImportDialog.tsx",
        "src/screens/ff/FfSellerCreateDialog.tsx",
        "src/screens/shared/MarkingImportDialog.tsx",
        "src/screens/shared/MarkingPoolProductsDialog.tsx",
        "src/screens/v2/FbsSupplyCreateDialog.tsx",
        "src/screens/v2/FfProductsCatalogScreen.tsx"
      ],
      "usages": 15
    },
    {
      "label": "Закрыть",
      "tones": [],
      "variants": [
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
        "src/screens/v2/FbsStockAllocationDialog.tsx",
        "src/screens/v2/FfProductsCatalogScreen.tsx",
        "src/screens/v2/SellerInboundDraftScreen.tsx",
        "src/screens/v2/SellerProductsStockScreen.tsx"
      ],
      "usages": 11
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
        "outlined/primary",
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
      "label": "К документам",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/v2/SellerInboundDraftScreen.tsx"
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
      "label": "Печать грузомест",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/ff/FfInboundRequestView.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Печать коробов",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/screens/ff/FfInboundRequestView.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Проставить",
      "tones": [],
      "variants": [
        "outlined/primary"
      ],
      "files": [
        "src/components/WbProductPickerDialog.tsx"
      ],
      "usages": 1
    },
    {
      "label": "Создать акт расхождений",
      "tones": [],
      "variants": [
        "text/inherit"
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
      "label": "info: Доступно только для фулфилмента.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/TransfersScreen.tsx"
      ],
      "usages": 1
    },
    {
      "label": "info: Нет доступа к сотрудникам.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfSettingsScreen.tsx"
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
      "label": "info: Нет товаров в плане отгрузки.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/ff/FfMpUnloadPickPanel.tsx"
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
      "label": "info: Новых заказов того же селлера и WB-склада нет.",
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
      "label": "warning: Нет доступа к этому разделу. Обратитесь к администратору селлера.",
      "tones": [],
      "variants": [],
      "files": [
        "src/apps/seller/SellerApp.tsx"
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
      "label": "warning: Создайте WMS-склад перед сопоставлением складов WB.",
      "tones": [],
      "variants": [],
      "files": [
        "src/screens/v2/FfFbsStockSyncScreen.tsx"
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
  ]
} as const satisfies
  Record<'chips' | 'statuses' | 'buttons' | 'alerts', readonly InventoryItem[]>
