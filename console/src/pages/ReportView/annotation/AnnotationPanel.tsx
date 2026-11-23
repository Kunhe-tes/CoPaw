/**
 * ！！！！注意代码不同步，不能合并
 */
import React, { useState } from "react";
import { Button, Input, Tooltip } from "antd";
import {
	EditOutlined,
	ReloadOutlined,
	CheckOutlined,
	CloseOutlined,
	DeleteOutlined,
	FileOutlined,
} from "@ant-design/icons";
import type { AnnotationItem } from "./useReportAnnotation";
import styles from "./annotation.module.less";

/** 工具栏属性 */
interface AnnotationToolbarProps {
	/** 是否处于意见模式 */
	annotationMode: boolean;
	/** 全选状态 */
	allSelected: boolean;
	/** 保存中 */
	saving: boolean;
	/** 意见数量 */
	annotationCount: number;
	/** 点击「意见 / 预览」切换模式 */
	onToggleMode: () => void;
	/** 点击「刷新」 */
	onRefresh: () => void;
	/** 点击「全选」 */
	onSelectAll: () => void;
	/** 点击「保存」 */
	onSave: () => void;
}

/**
 * 意见工具栏
 */
export function AnnotationToolbar({
	annotationMode,
	allSelected,
	saving,
	onToggleMode,
	onRefresh,
	onSelectAll,
	onSave,
}: AnnotationToolbarProps) {
	return (
		<div className={styles.annotationToolbar}>

		</div>
	);
}

/** 报告级意见（全选产生，始终展示在列表最顶部） */
export interface ReportAnnotationState {
	comment: string;
	status: "editing" | "preview";
}

/** 意见列表属性 */
interface AnnotationListProps {
	/** 意见列表 */
	annotations: AnnotationItem[];
	/** 报告级意见（全选产生，可为空） */
	reportAnnotation: ReportAnnotationState | null;
	/** 确认报告意见 */
	onConfirmReport: (comment: string) => void;
	/** 取消报告意见（移除卡片并退出全选） */
	onCancelReport: () => void;
	/** 编辑报告意见 */
	onEditReport: () => void;
	/** 点击卡片高亮对应元素 */
	onHighlight: (annotationId: string) => void;
	/** 确认意见（编辑态 → 预览态） */
	onConfirm: (annotationId: string, comment: string) => void;
	/** 取消意见（新增卡片 = 删除） */
	onCancel: (annotationId: string) => void;
	/** 删除意见 */
	onRemove: (annotationId: string) => void;
	/** 编辑意见（预览态 → 编辑态） */
	onEdit: (annotationId: string) => void;
}

export function AnnotationList(props: AnnotationListProps) {
	// const { annotations, reportAnnotation } = props;
	return (
		<div className={styles.annotationList}>
		</div>
	);
}
