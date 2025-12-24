import React, { useCallback, useEffect, useState } from 'react';

interface ResizeHandleProps {
  onResize: (deltaY: number) => void;
  onResizeEnd?: () => void;
}

export const ResizeHandle: React.FC<ResizeHandleProps> = ({ onResize, onResizeEnd }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [startY, setStartY] = useState(0);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    setStartY(e.clientY);
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaY = startY - e.clientY; // Negative = dragging down = more panel height
      onResize(deltaY);
      setStartY(e.clientY);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      onResizeEnd?.();
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, startY, onResize, onResizeEnd]);

  return (
    <div
      onMouseDown={handleMouseDown}
      className={`
        h-2 cursor-ns-resize flex items-center justify-center
        bg-app-bg hover:bg-app-border transition-colors
        ${isDragging ? 'bg-trading-blue' : ''}
      `}
    >
      <div className="w-12 h-1 rounded-full bg-app-border" />
    </div>
  );
};
